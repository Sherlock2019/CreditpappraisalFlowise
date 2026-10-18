#!/usr/bin/env node
/*
 * Offline validation for the generated Agentflow v2 files.
 *
 * 1. Graph: handles exist, every node is reachable from Start, no dangling nodes.
 * 2. References: every {{ nodeId }} / {{ nodeId.output.x }} points at an upstream node.
 * 3. Dry run: walks every branch with mocked FastAPI + LLM responses, executes the
 *    Custom Function code and resolves every HTTP body the same way Flowise 3.1 does,
 *    then checks each body parses as JSON and carries the fields FastAPI requires.
 *
 * Usage: node flowise_project/agentflows/validate-agentflows.js [file ...]
 */
const fs = require('fs')
const path = require('path')
const vm = require('vm')
const _get = (obj, p) => p.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj)

const GENERATED = path.join(__dirname, 'generated')
const files = process.argv.slice(2).length
    ? process.argv.slice(2)
    : fs
          .readdirSync(GENERATED)
          .filter((f) => f.endsWith('.json') && !f.endsWith('-api-import.json'))
          .map((f) => path.join(GENERATED, f))

// Required request fields per FastAPI endpoint (from bank-credit-ai-poc/backend/app).
const REQUIRED_FIELDS = {
    '/retrieval/query': ['customer_id', 'question'],
    '/loan-policy/score': ['customer_id'],
    '/approval-committee/submit': ['customer_id', 'submitted_by'],
    '/final-decision': ['customer_id', 'decision'],
    '/customer-decision-email/draft': ['customer_id'],
    '/audit': []
}
const DECISIONS = ['approved', 'rejected', 'conditional', 'deferred', 'request_more_info']

const VARS = {
    fastapi_base_url: 'http://fastapi.credit-ai.svc.cluster.local:8000',
    customer_id: 'CUST-001',
    session_id: 'sess-42',
    loan_amount: '250000',
    collateral_value: '400000',
    monthly_income: '12000',
    monthly_debt_payments: '1800',
    term_months: '60',
    officer_id: 'officer.nguyen',
    expected_decision: 'conditional'
}
const FLOW = { sessionId: 'sess-42', chatId: 'chat-1', chatflowId: 'flow-1', input: 'Please run a full credit appraisal for "CUST-001"', state: {} }

function mockHttp(urlPath, body, scenario) {
    switch (urlPath) {
        case '/retrieval/query': {
            const domain = (body.filters && body.filters.domain) || 'qa'
            const evidence = scenario.noEvidence
                ? []
                : [1, 2].map((i) => ({
                      chunk_id: `chunk_${domain}_${i}`,
                      document_id: `DOC-${domain}-${i}`,
                      document_name: `${domain}_doc_${i}.pdf`,
                      page: i,
                      text: `Evidence about ${domain} with "quotes" and\nnewlines ${i}`,
                      score: 0.8
                  }))
            return {
                customer_id: body.customer_id,
                evidence,
                missing_documents: scenario.missingDocs ? ['tax returns', domain === 'credit' ? 'x' : 'y'] : domain === 'asset' ? ['tax returns'] : []
            }
        }
        case '/loan-policy/score':
            return {
                policy_score_id: 7,
                customer_id: body.customer_id,
                dti: { value_pct: 15, band: 'low', assessment: 'ok' },
                ltv: { value_pct: 62.5, band: 'moderate', assessment: 'ok' },
                interest: { base_rate_pct: 6, risk_spread_pct: 1.5, estimated_annual_rate_pct: 7.5, estimated_monthly_payment: 5010 },
                policy: { recommendation: 'conditional', committee_required: true, reason_codes: ['LTV_MODERATE'] },
                fraud: { indicators: body.fraud_indicators, severity: 0 },
                missing_documents: body.missing_documents,
                next_steps: []
            }
        case '/approval-committee/submit':
            return { committee_case_id: 'COM-000012', status: 'submitted_to_committee', next_step: 'Final Decision' }
        case '/final-decision':
            return { decision_id: 'DEC-000034', status: 'final_decision_recorded' }
        case '/customer-decision-email/draft':
            return { email_draft_id: 'EML-000056', subject: 'Your application', body: '...', send_allowed: false }
        case '/audit':
            return { audit_id: 'audit_99', status: 'logged' }
        default:
            throw new Error(`No mock for ${urlPath}`)
    }
}

function mockLlm(node, scenario) {
    const structured = node.data.inputs.llmStructuredOutput
    if (!Array.isArray(structured) || !structured.length) {
        return { content: 'The customer has stable income [chunk_qa_1]. "Quoted" answer.\n\nSources: chunk_qa_1' }
    }
    const out = {}
    for (const s of structured) {
        if (s.type === 'enum') out[s.key] = s.enumValues.split(',')[1]?.trim() || s.enumValues.split(',')[0].trim()
        else if (s.type === 'number') out[s.key] = 0.9
        else if (s.type === 'boolean') out[s.key] = true
        else if (s.type === 'stringArray') out[s.key] = [`item "one" for ${s.key}`]
        else out[s.key] = `Text for ${s.key} with "quotes" and\nnewlines [chunk_credit_1]`
    }
    if ('missing_documents' in out) out.missing_documents = scenario.missingDocs ? ['collateral valuation'] : []
    if ('recommendation' in out) out.recommendation = 'conditional'
    if ('proposed_amount' in out) out.proposed_amount = 240000
    return { content: JSON.stringify(out, null, 2), ...out }
}

function validateFile(file) {
    const flow = JSON.parse(fs.readFileSync(file, 'utf8'))
    const errors = []
    const nodes = Object.fromEntries(flow.nodes.map((n) => [n.id, n]))
    const runnable = flow.nodes.filter((n) => n.type !== 'stickyNote')

    // ---- 1. graph ----
    const out = {}
    const incoming = {}
    for (const e of flow.edges) {
        if (!nodes[e.source] || !nodes[e.target]) errors.push(`edge ${e.id} references a missing node`)
        else if (!nodes[e.source].data.outputAnchors.some((a) => a.id === e.sourceHandle)) errors.push(`edge ${e.id} has unknown sourceHandle`)
        if (e.targetHandle !== e.target) errors.push(`edge ${e.id} targetHandle must equal target id`)
        ;(out[e.source] = out[e.source] || []).push(e)
        incoming[e.target] = (incoming[e.target] || 0) + 1
    }
    const start = runnable.filter((n) => n.data.name === 'startAgentflow')
    if (start.length !== 1) errors.push(`expected exactly 1 start node, found ${start.length}`)
    const reach = new Set()
    const stack = [start[0].id]
    while (stack.length) {
        const id = stack.pop()
        if (reach.has(id)) continue
        reach.add(id)
        for (const e of out[id] || []) stack.push(e.target)
    }
    for (const n of runnable) {
        if (!reach.has(n.id)) errors.push(`${n.id} (${n.data.label}) is not reachable from Start`)
        if (n.data.name !== 'startAgentflow' && !incoming[n.id]) errors.push(`${n.id} has no incoming edge`)
        if (n.data.outputAnchors.length && !out[n.id] && n.data.name !== 'directReplyAgentflow') errors.push(`${n.id} (${n.data.label}) has no outgoing edge`)
        for (const a of n.data.outputAnchors) {
            if (n.data.outputAnchors.length > 1 && !(out[n.id] || []).some((e) => e.sourceHandle === a.id)) errors.push(`${a.id} is not connected`)
        }
    }
    const labels = runnable.map((n) => n.data.label)
    for (const l of new Set(labels)) if (labels.filter((x) => x === l).length > 1) errors.push(`duplicate node label "${l}"`)

    // ancestors for reference checks
    const parents = {}
    for (const e of flow.edges) (parents[e.target] = parents[e.target] || []).push(e.source)
    const ancestors = (id, acc = new Set()) => {
        for (const p of parents[id] || []) if (!acc.has(p)) acc.add(p), ancestors(p, acc)
        return acc
    }

    // ---- 2. references ----
    for (const n of runnable) {
        const text = JSON.stringify(n.data.inputs)
        const up = ancestors(n.id)
        for (const m of text.matchAll(/{{\s*([A-Za-z]+Agentflow_\d+)/g)) {
            if (!nodes[m[1]]) errors.push(`${n.id} references missing node ${m[1]}`)
            else if (!up.has(m[1])) errors.push(`${n.id} (${n.data.label}) references ${m[1]} which is not upstream`)
        }
        if (n.data.name === 'customFunctionAgentflow') {
            try {
                new vm.Script(`(async () => {\n${n.data.inputs.customFunctionJavascriptFunction}\n})`)
            } catch (err) {
                errors.push(`${n.id} (${n.data.label}) code does not compile: ${err.message}`)
            }
        }
    }

    // ---- 3. dry run every branch ----
    const scenarios = [
        { name: 'appraisal → proceed', route: 0, human: 0 },
        { name: 'appraisal → reject', route: 0, human: 1 },
        { name: 'appraisal → missing documents', route: 0, missingDocs: true },
        { name: 'appraisal → no evidence', route: 0, noEvidence: true },
        { name: 'loan officer Q&A', route: 1 }
    ]
    const results = []
    for (const scenario of scenarios) {
        try {
            results.push(`${scenario.name}: ${dryRun(flow, nodes, out, start[0].id, scenario)}`)
        } catch (err) {
            errors.push(`[${scenario.name}] ${err.message}`)
        }
    }
    return { errors, results, flow }
}

function resolve(value, executed) {
    if (typeof value !== 'string') return value
    let resolved = value
    for (const match of value.match(/{{(.*?)}}/g) || []) {
        const ref = match.replace(/[{}]/g, '').trim()
        let v
        if (ref === 'question') v = FLOW.input
        else if (ref.startsWith('$vars.')) v = VARS[ref.slice(6)]
        else if (ref.startsWith('$flow.')) v = _get(FLOW, ref.slice(6))
        else {
            const om = ref.match(/^(.*?)\.output\.(.+)$/)
            const id = om ? om[1] : ref
            if (!executed[id]) throw new Error(`reference ${ref} resolved before ${id} ran`)
            v = om ? _get(executed[id], om[2]) : executed[id].content ?? executed[id].http?.data
        }
        if (v === undefined) throw new Error(`reference ${ref} resolved to undefined`)
        const formatted = typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)
        resolved = resolved === match ? formatted : resolved.replace(match, formatted)
    }
    return resolved
}

function runCustomFunction(node, executed) {
    const sandbox = { $vars: VARS, $flow: FLOW, JSON, Number, String, Math, Date, Set, Error, Object, Array }
    for (const v of node.data.inputs.customFunctionInputVariables || []) sandbox[`$${v.variableName}`] = resolve(v.variableValue, executed)
    const code = `(function () {\n${node.data.inputs.customFunctionJavascriptFunction}\n})()`
    const result = vm.runInNewContext(code, sandbox, { timeout: 1000 })
    return typeof result === 'object' ? JSON.stringify(result, null, 2) : String(result)
}

function dryRun(flow, nodes, out, startId, scenario) {
    const executed = {}
    const path = []
    let current = startId
    for (let guard = 0; current && guard < 100; guard++) {
        const node = nodes[current]
        const name = node.data.name
        const inputs = node.data.inputs
        path.push(node.data.label)
        let branch
        if (name === 'startAgentflow') executed[current] = { content: FLOW.input }
        else if (name === 'customFunctionAgentflow') executed[current] = { content: runCustomFunction(node, executed) }
        else if (name === 'conditionAgentAgentflow') branch = scenario.route
        else if (name === 'conditionAgentflow') {
            const c = inputs.conditions[0]
            const left = resolve(c.value1, executed)
            const ok = c.operation === 'startsWith' ? left.startsWith(c.value2) : left === c.value2
            branch = ok ? 0 : 1
            executed[current] = { content: left }
        } else if (name === 'llmAgentflow') {
            for (const m of inputs.llmMessages) resolve(m.content, executed)
            executed[current] = mockLlm(node, scenario)
        } else if (name === 'humanInputAgentflow') {
            resolve(inputs.humanInputDescription, executed)
            branch = scenario.human ?? 0
            executed[current] = { content: branch === 0 ? 'Looks good, proceed' : 'Collateral valuation is outdated' }
        } else if (name === 'httpAgentflow') {
            const url = resolve(inputs.url, executed)
            const urlPath = url.replace(VARS.fastapi_base_url, '')
            let body = {}
            if (inputs.method !== 'GET') {
                const raw = resolve(inputs.body, executed)
                try {
                    body = JSON.parse(raw)
                } catch (err) {
                    throw new Error(`${node.data.label}: body is not valid JSON (${err.message}): ${raw.slice(0, 300)}`)
                }
            }
            for (const f of REQUIRED_FIELDS[urlPath] || []) {
                if (body[f] === undefined || body[f] === null || body[f] === '') throw new Error(`${node.data.label}: missing ${f}`)
            }
            if (urlPath === '/final-decision' && !DECISIONS.includes(body.decision)) throw new Error(`${node.data.label}: invalid decision ${body.decision}`)
            if (urlPath === '/loan-policy/score' && !(body.monthly_income > 0)) throw new Error(`${node.data.label}: monthly_income not coerced to a number`)
            for (const h of inputs.headers || []) resolve(h.value, executed)
            executed[current] = { http: { data: mockHttp(urlPath, body, scenario), status: 200 } }
        } else if (name === 'directReplyAgentflow') {
            const message = resolve(inputs.directReplyMessage, executed)
            if (!message.trim()) throw new Error(`${node.data.label}: empty reply`)
            return `${path.length} nodes → "${message.split('\n').find((l) => l.trim()).slice(0, 70)}"`
        }
        const edges = out[current] || []
        const next = branch === undefined ? edges[0] : edges.find((e) => e.sourceHandle.endsWith(`-output-${branch}`))
        if (!next) throw new Error(`${node.data.label}: no outgoing edge for branch ${branch}`)
        current = next.target
    }
    throw new Error('flow did not reach a Direct Reply node')
}

let failed = false
for (const file of files) {
    const { errors, results, flow } = validateFile(file)
    console.log(`\n${path.basename(file)} (${flow.nodes.length} nodes, ${flow.edges.length} edges)`)
    for (const r of results) console.log(`  ok  ${r}`)
    for (const e of errors) console.log(`  ERR ${e}`)
    if (errors.length) failed = true
}
process.exit(failed ? 1 : 0)
