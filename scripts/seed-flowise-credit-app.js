// Seed the credit appraisal RAG flow into the local Flowise database.
//
// The flow is a real Flowise pipeline built from stock nodes:
//
//   Folder with Files --(chunks)--> Postgres (pgvector) <-- Ollama Embedding
//          ^                              |
//   Recursive Character Text Splitter     v retriever
//                 Ollama chat model --> Conversational Retrieval QA Chain
//
// FastAPI calls it through /api/v1/prediction/<flow id>; documents are chunked,
// embedded and stored with /api/v1/vector/upsert/<flow id>.
//
// Environment (all optional):
//   FLOWISE_OLLAMA_BASE_URL   default http://127.0.0.1:11434
//   FLOWISE_OLLAMA_MODEL      chat model, default mistral:7b-instruct
//   FLOWISE_EMBEDDING_MODEL   embedding model, default embeddinggemma
//   FLOWISE_RAG_DOCUMENTS_DIR folder that is chunked and embedded, relative to bank-credit-ai-poc
//   FLOWISE_RAG_PG_HOST / _PORT / _DATABASE / _TABLE   pgvector location
//   SEED_UPDATE_ENV=0         leave bank-credit-ai-poc/.env and the exported flow file untouched
//
// The PostgreSQL user and password are read by Flowise itself from
// POSTGRES_VECTORSTORE_USER / POSTGRES_VECTORSTORE_PASSWORD (set by start-flowise.sh).
const fs = require("fs");
const path = require("path");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");

const root = path.join(__dirname, "..");
const dbPath = path.join(root, "bank-credit-ai-poc", "flowise", ".flowise", "database.sqlite");
const envPath = path.join(root, "bank-credit-ai-poc", ".env");
const flowPath = path.join(root, "bank-credit-ai-poc", "flowise", "flows", "docfactor_credit_appraisal_rag_backend.json");

const legacyFlowId = "docfactor-credit-appraisal-rag-backend";
const flowId = process.env.FLOWISE_CHATFLOW_ID && process.env.FLOWISE_CHATFLOW_ID !== legacyFlowId
  ? process.env.FLOWISE_CHATFLOW_ID
  : "6f946e8b-2d35-4fd4-9ff9-158db1f0b820";
const flowName = "Docfactor Credit Appraisal RAG Workflow";

const ollamaBaseUrl = process.env.FLOWISE_OLLAMA_BASE_URL || "http://127.0.0.1:11434";
const chatModel = process.env.FLOWISE_OLLAMA_MODEL || "mistral:7b-instruct";
const embeddingModel = process.env.FLOWISE_EMBEDDING_MODEL || "embeddinggemma";
// Flowise only accepts folder paths relative to its working directory (bank-credit-ai-poc),
// so flowise/rag-documents is a link to docfactor_banking_demo_dataset/customer_documents.
const documentsDir = process.env.FLOWISE_RAG_DOCUMENTS_DIR || "flowise/rag-documents";
const pgHost = process.env.FLOWISE_RAG_PG_HOST || "localhost";
const pgPort = process.env.FLOWISE_RAG_PG_PORT || "5432";
const pgDatabase = process.env.FLOWISE_RAG_PG_DATABASE || "credit_ai";
const pgTable = process.env.FLOWISE_RAG_PG_TABLE || "flowise_rag_chunks";

const responsePrompt = `You are a banking credit analysis assistant.

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

Retrieved context from the PostgreSQL vector store:
{context}`;

const rephrasePrompt = `Given the following conversation and a follow up question, rephrase the follow up question to be a standalone question.

Chat History:
{chat_history}
Follow Up Input: {question}
Standalone Question:`;

// Input types that Flowise renders as form fields; every other type is a connection anchor.
const PARAM_TYPES = new Set(["string", "number", "boolean", "options", "json", "password", "credential"]);

// Node definitions mirror flowise-components 3.1.2 (name, version, inputs and outputs).
const NODE_SPECS = {
  recursiveCharacterTextSplitter: {
    label: "Recursive Character Text Splitter",
    type: "RecursiveCharacterTextSplitter",
    version: 2,
    category: "Text Splitters",
    description: "Split documents recursively by different characters - starting with \"\\n\\n\", then \"\\n\", then \" \"",
    baseClasses: ["RecursiveCharacterTextSplitter", "TextSplitter", "BaseDocumentTransformer", "Runnable"],
    inputs: [
      { label: "Chunk Size", name: "chunkSize", type: "number", default: 1000, optional: true },
      { label: "Chunk Overlap", name: "chunkOverlap", type: "number", default: 200, optional: true },
      { label: "Custom Separators", name: "separators", type: "string", rows: 4, optional: true, additionalParams: true },
    ],
  },
  folderFiles: {
    label: "Folder with Files",
    type: "Document",
    version: 4,
    category: "Document Loaders",
    description: "Load data from folder with multiple files",
    baseClasses: ["Document"],
    inputs: [
      { label: "Folder Path", name: "folderPath", type: "string" },
      { label: "Recursive", name: "recursive", type: "boolean" },
      { label: "Text Splitter", name: "textSplitter", type: "TextSplitter", optional: true },
      {
        label: "Pdf Usage", name: "pdfUsage", type: "options", default: "perPage", optional: true, additionalParams: true,
        options: [{ label: "One document per page", name: "perPage" }, { label: "One document per file", name: "perFile" }],
      },
      { label: "JSONL Pointer Extraction", name: "pointerName", type: "string", optional: true, additionalParams: true },
      { label: "Additional Metadata", name: "metadata", type: "json", optional: true, additionalParams: true },
      { label: "Omit Metadata Keys", name: "omitMetadataKeys", type: "string", rows: 4, optional: true, additionalParams: true },
    ],
    outputs: [
      { label: "Document", name: "document", baseClasses: ["Document", "json"] },
      { label: "Text", name: "text", baseClasses: ["string", "json"] },
    ],
  },
  ollamaEmbedding: {
    label: "Ollama Embedding",
    type: "OllamaEmbeddings",
    version: 2,
    category: "Embeddings",
    description: "Generate embeddings for a given text using open source model on Ollama",
    baseClasses: ["OllamaEmbeddings", "Embeddings"],
    inputs: [
      { label: "Base URL", name: "baseUrl", type: "string", default: "http://localhost:11434" },
      { label: "Model Name", name: "modelName", type: "string", placeholder: "all-minilm" },
      { label: "Number of GPU", name: "numGpu", type: "number", optional: true, additionalParams: true },
      { label: "Number of Thread", name: "numThread", type: "number", optional: true, additionalParams: true },
      { label: "Use MMap", name: "useMMap", type: "boolean", default: true, optional: true, additionalParams: true },
    ],
  },
  postgres: {
    label: "Postgres",
    type: "Postgres",
    version: 7.1,
    category: "Vector Stores",
    description: "Upsert embedded data and perform similarity search upon query using pgvector on Postgres",
    baseClasses: ["Postgres", "VectorStoreRetriever", "BaseRetriever"],
    // Optional because Flowise reads POSTGRES_VECTORSTORE_USER / POSTGRES_VECTORSTORE_PASSWORD from its environment.
    credential: { label: "Connect Credential", name: "credential", type: "credential", credentialNames: ["PostgresApi"], optional: true },
    inputs: [
      { label: "Document", name: "document", type: "Document", list: true, optional: true },
      { label: "Embeddings", name: "embeddings", type: "Embeddings" },
      { label: "Record Manager", name: "recordManager", type: "RecordManager", optional: true },
      { label: "Host", name: "host", type: "string" },
      { label: "Database", name: "database", type: "string" },
      { label: "Port", name: "port", type: "number", optional: true },
      { label: "SSL", name: "ssl", type: "boolean", optional: true, additionalParams: true },
      { label: "Table Name", name: "tableName", type: "string", optional: true, additionalParams: true },
      {
        label: "Distance Strategy", name: "distanceStrategy", type: "options", default: "cosine", optional: true, additionalParams: true,
        options: [{ label: "Cosine", name: "cosine" }, { label: "Euclidean", name: "euclidean" }, { label: "Inner Product", name: "innerProduct" }],
      },
      { label: "File Upload", name: "fileUpload", type: "boolean", optional: true, additionalParams: true },
      { label: "Upsert Batch Size", name: "batchSize", type: "number", optional: true, additionalParams: true },
      { label: "Additional Configuration", name: "additionalConfig", type: "json", optional: true, additionalParams: true },
      { label: "Top K", name: "topK", type: "number", optional: true, additionalParams: true },
      { label: "Postgres Metadata Filter", name: "pgMetadataFilter", type: "json", optional: true, additionalParams: true },
      { label: "Content Column Name", name: "contentColumnName", type: "string", optional: true, additionalParams: true },
    ],
    outputs: [
      { label: "Postgres Retriever", name: "retriever", baseClasses: ["Postgres", "VectorStoreRetriever", "BaseRetriever"] },
      { label: "Postgres Vector Store", name: "vectorStore", baseClasses: ["Postgres", "VectorStore"] },
    ],
  },
  chatOllama: {
    label: "Ollama",
    type: "ChatOllama",
    version: 5,
    category: "Chat Models",
    description: "Chat completion using open-source LLM on Ollama",
    baseClasses: ["ChatOllama", "BaseChatModel", "BaseLanguageModel", "Runnable"],
    inputs: [
      { label: "Cache", name: "cache", type: "BaseCache", optional: true },
      { label: "Base URL", name: "baseUrl", type: "string", default: "http://localhost:11434" },
      { label: "Model Name", name: "modelName", type: "string", placeholder: "llama2" },
      { label: "Temperature", name: "temperature", type: "number", step: 0.1, default: 0.9, optional: true },
      { label: "Streaming", name: "streaming", type: "boolean", default: true, optional: true, additionalParams: true },
      { label: "Keep Alive", name: "keepAlive", type: "string", default: "5m", optional: true, additionalParams: true },
      { label: "Context Window Size", name: "numCtx", type: "number", step: 1, optional: true, additionalParams: true },
    ],
  },
  conversationalRetrievalQAChain: {
    label: "Conversational Retrieval QA Chain",
    type: "ConversationalRetrievalQAChain",
    version: 3,
    category: "Chains",
    description: "Document QA - built on RetrievalQAChain to provide a chat history component",
    baseClasses: ["ConversationalRetrievalQAChain", "BaseChain", "Runnable"],
    inputs: [
      { label: "Chat Model", name: "model", type: "BaseChatModel" },
      { label: "Vector Store Retriever", name: "vectorStoreRetriever", type: "BaseRetriever" },
      { label: "Memory", name: "memory", type: "BaseMemory", optional: true },
      { label: "Return Source Documents", name: "returnSourceDocuments", type: "boolean", optional: true },
      { label: "Rephrase Prompt", name: "rephrasePrompt", type: "string", rows: 4, optional: true, additionalParams: true },
      { label: "Response Prompt", name: "responsePrompt", type: "string", rows: 4, optional: true, additionalParams: true },
      { label: "Input Moderation", name: "inputModeration", type: "Moderation", list: true, optional: true },
    ],
  },
};

function outputHandle(nodeId, name, baseClasses) {
  return `${nodeId}-output-${name}-${baseClasses.join("|")}`;
}

function buildNode(name, index, position, inputs, selectedOutput) {
  const spec = NODE_SPECS[name];
  const id = `${name}_${index}`;
  const withId = (input) => ({ ...input, id: `${id}-input-${input.name}-${input.type}` });
  const fields = [...(spec.credential ? [spec.credential] : []), ...spec.inputs];

  const defaults = {};
  for (const input of spec.inputs) defaults[input.name] = input.default !== undefined ? input.default : "";

  const outputAnchors = spec.outputs
    ? [{
        name: "output",
        label: "Output",
        type: "options",
        description: "",
        options: spec.outputs.map((output) => ({
          id: outputHandle(id, output.name, output.baseClasses),
          name: output.name,
          label: output.label,
          description: "",
          type: output.baseClasses.join(" | "),
        })),
        default: spec.outputs[0].name,
      }]
    : [{
        id: outputHandle(id, name, spec.baseClasses),
        name,
        label: spec.type,
        description: spec.description,
        type: spec.baseClasses.join(" | "),
      }];

  return {
    id,
    position,
    positionAbsolute: position,
    type: "customNode",
    width: 300,
    height: 420,
    selected: false,
    dragging: false,
    data: {
      id,
      label: spec.label,
      version: spec.version,
      name,
      type: spec.type,
      baseClasses: spec.baseClasses,
      category: spec.category,
      description: spec.description,
      inputParams: fields.filter((input) => PARAM_TYPES.has(input.type)).map(withId),
      inputAnchors: fields.filter((input) => !PARAM_TYPES.has(input.type)).map(withId),
      inputs: { ...defaults, ...inputs },
      outputAnchors,
      outputs: spec.outputs ? { output: selectedOutput || spec.outputs[0].name } : {},
      selected: false,
    },
  };
}

function sourceHandleOf(node) {
  const [anchor] = node.data.outputAnchors;
  if (!anchor.options) return anchor.id;
  return anchor.options.find((option) => option.name === node.data.outputs.output).id;
}

function connect(source, target, inputName) {
  const anchor = target.data.inputAnchors.find((input) => input.name === inputName);
  const reference = `{{${source.id}.data.instance}}`;
  target.data.inputs[inputName] = anchor.list ? [reference] : reference;
  const sourceHandle = sourceHandleOf(source);
  return {
    source: source.id,
    sourceHandle,
    target: target.id,
    targetHandle: anchor.id,
    type: "buttonedge",
    id: `${source.id}-${sourceHandle}-${target.id}-${anchor.id}`,
  };
}

// Positions leave room for each node's full height so nothing overlaps on the canvas.
const splitter = buildNode("recursiveCharacterTextSplitter", 0, { x: 0, y: 40 }, {
  chunkSize: 1000,
  chunkOverlap: 200,
});
const loader = buildNode("folderFiles", 0, { x: 400, y: 40 }, {
  folderPath: documentsDir,
  recursive: true,
  pdfUsage: "perPage",
}, "document");
const embeddings = buildNode("ollamaEmbedding", 0, { x: 400, y: 640 }, {
  baseUrl: ollamaBaseUrl,
  modelName: embeddingModel,
});
const vectorStore = buildNode("postgres", 0, { x: 820, y: 200 }, {
  host: pgHost,
  database: pgDatabase,
  port: pgPort,
  tableName: pgTable,
  distanceStrategy: "cosine",
  topK: 6,
}, "retriever");
const chat = buildNode("chatOllama", 0, { x: 820, y: 1020 }, {
  baseUrl: ollamaBaseUrl,
  modelName: chatModel,
  temperature: 0.2,
  streaming: true,
  numCtx: 8192,
});
const chain = buildNode("conversationalRetrievalQAChain", 0, { x: 1260, y: 560 }, {
  returnSourceDocuments: true,
  rephrasePrompt,
  responsePrompt,
});

const flowData = {
  nodes: [splitter, loader, embeddings, vectorStore, chat, chain],
  edges: [
    connect(splitter, loader, "textSplitter"),
    connect(loader, vectorStore, "document"),
    connect(embeddings, vectorStore, "embeddings"),
    connect(vectorStore, chain, "vectorStoreRetriever"),
    connect(chat, chain, "model"),
  ],
  viewport: { x: 40, y: 20, zoom: 0.5 },
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
    // Let API callers (FastAPI) narrow retrieval to one customer through the Postgres metadata filter.
    const metadataFilterOverride = [{
      nodeId: vectorStore.id,
      label: "Postgres Metadata Filter",
      name: "pgMetadataFilter",
      type: "json",
      enabled: true,
    }];
    const apiConfig = JSON.stringify({
      overrideConfig: {
        status: true,
        nodes: { [vectorStore.data.label]: metadataFilterOverride, [vectorStore.data.name]: metadataFilterOverride },
        variables: [],
      },
    });

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

        // SEED_UPDATE_ENV=0 seeds the database only and leaves the tracked files untouched.
        if (process.env.SEED_UPDATE_ENV !== "0") {
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
        }

        console.log(JSON.stringify({
          id: flowId,
          name: flowName,
          workspaceId,
          nodes: flowData.nodes.map((node) => node.data.label),
          chat_model: chatModel,
          embedding_model: embeddingModel,
          vector_store: `${pgHost}:${pgPort}/${pgDatabase}.${pgTable}`,
          documents: documentsDir,
        }, null, 2));
        db.close();
      }
    );
  });
});
