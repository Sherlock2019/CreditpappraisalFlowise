const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");

const root = path.join(__dirname, "..");
const dbPath = path.join(root, "bank-credit-ai-poc", "flowise", ".flowise", "database.sqlite");
const envPath = path.join(root, "bank-credit-ai-poc", ".env");
const flowPath = path.join(root, "bank-credit-ai-poc", "flowise", "flows", "docfactor_credit_appraisal_rag_backend.json");

const legacyFlowId = "docfactor-credit-appraisal-rag-backend";
const flowId = process.env.FLOWISE_CHATFLOW_ID && process.env.FLOWISE_CHATFLOW_ID !== legacyFlowId
  ? process.env.FLOWISE_CHATFLOW_ID
  : "6f946e8b-2d35-4fd4-9ff9-158db1f0b820";
const flowName = "Docfactor Credit Appraisal RAG Backend";

const systemPrompt = `You are a banking credit analysis assistant.

You provide decision support only. You must not approve or reject loans.

Use only the provided context from customer documents and bank policies.
If evidence is missing, say what is missing.
Always include citations using document name and page number when available.
Always include: "Human credit officer review required."

Return the answer using this structure:

1. Short Answer
2. Risk Level: Low / Medium / High / Insufficient Evidence
3. Preliminary Heuristic Score if available
4. Key Evidence
5. Strengths
6. Weaknesses / Risks
7. Missing Documents or Data
8. Suggested Follow-up Questions
9. Citations
10. Human Review Required

Do not invent facts.
Do not expose unnecessary sensitive personal data.
Do not make a final credit decision.

Customer ID: {customer_id}
Retrieved context:
{context}

User question:
{question}`;

const flowData = {
  nodes: [
    {
      width: 300,
      height: 560,
      id: "chatOllama_0",
      position: { x: 80, y: 160 },
      type: "customNode",
      data: {
        id: "chatOllama_0",
        label: "Ollama",
        version: 5,
        name: "chatOllama",
        type: "ChatOllama",
        baseClasses: ["ChatOllama", "BaseChatModel", "BaseLanguageModel", "Runnable"],
        category: "Chat Models",
        description: "Chat completion using open-source LLM on local Ollama",
        inputParams: [
          {
            label: "Base URL",
            name: "baseUrl",
            type: "string",
            default: "http://127.0.0.1:11434",
            id: "chatOllama_0-input-baseUrl-string"
          },
          {
            label: "Model Name",
            name: "modelName",
            type: "string",
            placeholder: "mistral:7b-instruct",
            id: "chatOllama_0-input-modelName-string"
          },
          {
            label: "Temperature",
            name: "temperature",
            type: "number",
            step: 0.1,
            default: 0.2,
            optional: true,
            id: "chatOllama_0-input-temperature-number"
          },
          {
            label: "Streaming",
            name: "streaming",
            type: "boolean",
            default: true,
            optional: true,
            additionalParams: true,
            id: "chatOllama_0-input-streaming-boolean"
          },
          {
            label: "Context Window Size",
            name: "numCtx",
            type: "number",
            step: 1,
            optional: true,
            additionalParams: true,
            id: "chatOllama_0-input-numCtx-number"
          }
        ],
        inputAnchors: [],
        inputs: {
          baseUrl: "http://127.0.0.1:11434",
          modelName: "mistral:7b-instruct",
          temperature: "0.2",
          streaming: true,
          numCtx: "4096"
        },
        outputAnchors: [
          {
            id: "chatOllama_0-output-chatOllama-ChatOllama|BaseChatModel|BaseLanguageModel|Runnable",
            name: "chatOllama",
            label: "Ollama",
            type: "ChatOllama | BaseChatModel | BaseLanguageModel | Runnable"
          }
        ],
        outputs: {},
        selected: false
      },
      selected: false,
      positionAbsolute: { x: 80, y: 160 },
      dragging: false
    },
    {
      width: 360,
      height: 620,
      id: "promptTemplate_0",
      position: { x: 460, y: 100 },
      type: "customNode",
      data: {
        id: "promptTemplate_0",
        label: "Prompt Template",
        version: 1,
        name: "promptTemplate",
        type: "PromptTemplate",
        baseClasses: ["PromptTemplate", "BaseStringPromptTemplate", "BasePromptTemplate"],
        category: "Prompts",
        description: "Banking credit appraisal safety prompt with retrieved document context",
        inputParams: [
          {
            label: "Template",
            name: "template",
            type: "string",
            rows: 4,
            id: "promptTemplate_0-input-template-string"
          },
          {
            label: "Format Prompt Values",
            name: "promptValues",
            type: "json",
            optional: true,
            acceptVariable: true,
            list: true,
            id: "promptTemplate_0-input-promptValues-json"
          }
        ],
        inputAnchors: [],
        inputs: {
          template: systemPrompt,
          promptValues: JSON.stringify({
            question: "{{question}}",
            customer_id: "{{$vars.customer_id}}",
            context: "{{$vars.context}}"
          })
        },
        outputAnchors: [
          {
            id: "promptTemplate_0-output-promptTemplate-PromptTemplate|BaseStringPromptTemplate|BasePromptTemplate",
            name: "promptTemplate",
            label: "PromptTemplate",
            type: "PromptTemplate | BaseStringPromptTemplate | BasePromptTemplate"
          }
        ],
        outputs: {},
        selected: false
      },
      selected: false,
      positionAbsolute: { x: 460, y: 100 },
      dragging: false
    },
    {
      width: 300,
      height: 520,
      id: "llmChain_0",
      position: { x: 900, y: 180 },
      type: "customNode",
      data: {
        id: "llmChain_0",
        label: "LLM Chain",
        version: 3,
        name: "llmChain",
        type: "LLMChain",
        baseClasses: ["LLMChain", "BaseChain", "Runnable"],
        category: "Chains",
        description: "Flowise backend chain for Docfactor credit appraisal answers",
        inputParams: [
          {
            label: "Chain Name",
            name: "chainName",
            type: "string",
            placeholder: "Name Your Chain",
            optional: true,
            id: "llmChain_0-input-chainName-string"
          }
        ],
        inputAnchors: [
          {
            label: "Language Model",
            name: "model",
            type: "BaseLanguageModel",
            id: "llmChain_0-input-model-BaseLanguageModel"
          },
          {
            label: "Prompt",
            name: "prompt",
            type: "BasePromptTemplate",
            id: "llmChain_0-input-prompt-BasePromptTemplate"
          },
          {
            label: "Output Parser",
            name: "outputParser",
            type: "BaseLLMOutputParser",
            optional: true,
            id: "llmChain_0-input-outputParser-BaseLLMOutputParser"
          }
        ],
        inputs: {
          model: "{{chatOllama_0.data.instance}}",
          prompt: "{{promptTemplate_0.data.instance}}",
          outputParser: "",
          chainName: "Docfactor Credit Appraisal RAG Backend"
        },
        outputAnchors: [
          {
            name: "output",
            label: "Output",
            type: "options",
            options: [
              {
                id: "llmChain_0-output-llmChain-LLMChain|BaseChain|Runnable",
                name: "llmChain",
                label: "LLM Chain",
                type: "LLMChain | BaseChain | Runnable"
              },
              {
                id: "llmChain_0-output-outputPrediction-string|json",
                name: "outputPrediction",
                label: "Output Prediction",
                type: "string | json"
              }
            ],
            default: "llmChain"
          }
        ],
        outputs: { output: "llmChain" },
        selected: false
      },
      selected: false,
      positionAbsolute: { x: 900, y: 180 },
      dragging: false
    }
  ],
  edges: [
    {
      source: "chatOllama_0",
      sourceHandle: "chatOllama_0-output-chatOllama-ChatOllama|BaseChatModel|BaseLanguageModel|Runnable",
      target: "llmChain_0",
      targetHandle: "llmChain_0-input-model-BaseLanguageModel",
      type: "buttonedge",
      id: "chatOllama_0-chatOllama_0-output-chatOllama-ChatOllama|BaseChatModel|BaseLanguageModel|Runnable-llmChain_0-llmChain_0-input-model-BaseLanguageModel"
    },
    {
      source: "promptTemplate_0",
      sourceHandle: "promptTemplate_0-output-promptTemplate-PromptTemplate|BaseStringPromptTemplate|BasePromptTemplate",
      target: "llmChain_0",
      targetHandle: "llmChain_0-input-prompt-BasePromptTemplate",
      type: "buttonedge",
      id: "promptTemplate_0-promptTemplate_0-output-promptTemplate-PromptTemplate|BaseStringPromptTemplate|BasePromptTemplate-llmChain_0-llmChain_0-input-prompt-BasePromptTemplate"
    }
  ],
  viewport: { x: 0, y: 0, zoom: 0.85 }
};

function updateEnv(content, key, value) {
  const line = `${key}=${value}`;
  if (content.match(new RegExp(`^${key}=.*$`, "m"))) {
    return content.replace(new RegExp(`^${key}=.*$`, "m"), line);
  }
  return `${content.trimEnd()}\n${line}\n`;
}

const db = new sqlite3.Database(dbPath);

db.serialize(() => {
  db.get("select id from workspace order by createdDate limit 1", (workspaceError, workspace) => {
    if (workspaceError) throw workspaceError;
    const workspaceId = workspace?.id;
    if (!workspaceId) {
      throw new Error("No Flowise workspace found. Start Flowise once before seeding the credit app flow.");
    }

    const now = new Date().toISOString();
    const flowDataJson = JSON.stringify(flowData);
    const chatbotConfig = JSON.stringify({
      starterPrompts: [
        "Summarize this customer's credit risk.",
        "What documents are missing for a complete credit review?",
        "Give me a preliminary risk level with citations."
      ]
    });
    const apiConfig = JSON.stringify({ overrideConfig: true });

    db.run(
      "delete from chat_flow where id = ?",
      [legacyFlowId],
      (deleteError) => {
        if (deleteError) throw deleteError;
      }
    );

    db.run(
      `insert into chat_flow
        (id, name, flowData, deployed, isPublic, chatbotConfig, apiConfig, category, type, workspaceId, createdDate, updatedDate)
       values (?, ?, ?, 1, 1, ?, ?, 'Banking Credit Appraisal', 'CHATFLOW', ?, ?, ?)
       on conflict(id) do update set
        name = excluded.name,
        flowData = excluded.flowData,
        deployed = 1,
        isPublic = 1,
        chatbotConfig = excluded.chatbotConfig,
        apiConfig = excluded.apiConfig,
        category = excluded.category,
        type = excluded.type,
        workspaceId = excluded.workspaceId,
        updatedDate = excluded.updatedDate`,
      [flowId, flowName, flowDataJson, chatbotConfig, apiConfig, workspaceId, now, now],
      (flowError) => {
        if (flowError) throw flowError;

        fs.mkdirSync(path.dirname(flowPath), { recursive: true });
        fs.writeFileSync(flowPath, JSON.stringify({ id: flowId, name: flowName, ...flowData }, null, 2));

        if (fs.existsSync(envPath)) {
          let env = fs.readFileSync(envPath, "utf8");
          env = updateEnv(env, "FLOWISE_API_URL", "http://host.docker.internal:3001");
          env = updateEnv(env, "FLOWISE_CHATFLOW_ID", flowId);
          env = updateEnv(env, "LLM_PROVIDER", "local_mistral_ollama");
          env = updateEnv(env, "OLLAMA_BASE_URL", "http://127.0.0.1:11434");
          env = updateEnv(env, "OLLAMA_MODEL", "mistral:7b-instruct");
          fs.writeFileSync(envPath, env);
        }

        console.log(JSON.stringify({ id: flowId, name: flowName, workspaceId }, null, 2));
        db.close();
      }
    );
  });
});
