"""GENERADO por `scripts/gen_semconv.py`. NO SE EDITA A MANO.

Nombres externos de OpenTelemetry, renderizados desde el snapshot vendorizado del commit
que fija `otel-semconv.lock`. El modelo interno no usa ninguno de estos nombres: el
traductor es el único módulo que los conoce (contrato otel-genai §2), y R5 impide que un
literal `gen_ai.*` aparezca fuera de aquí.

Subir la versión es un cambio consciente: entrada en CHANGELOG y revisión del traductor.
"""

SEMCONV_REPO = "open-telemetry/semantic-conventions"
SEMCONV_VERSION = "v1.41.1"
SEMCONV_COMMIT = "ead83b9b0fa36540c1642fce46e874f002ac23f1"

# --- Atributos ---
ERROR_TYPE = "error.type"
AGENT_DESCRIPTION = "gen_ai.agent.description"
AGENT_ID = "gen_ai.agent.id"
AGENT_NAME = "gen_ai.agent.name"
AGENT_VERSION = "gen_ai.agent.version"
CONVERSATION_ID = "gen_ai.conversation.id"
DATA_SOURCE_ID = "gen_ai.data_source.id"
EMBEDDINGS_DIMENSION_COUNT = "gen_ai.embeddings.dimension.count"
EVALUATION_EXPLANATION = "gen_ai.evaluation.explanation"
EVALUATION_NAME = "gen_ai.evaluation.name"
EVALUATION_SCORE_LABEL = "gen_ai.evaluation.score.label"
EVALUATION_SCORE_VALUE = "gen_ai.evaluation.score.value"
INPUT_MESSAGES = "gen_ai.input.messages"
OPERATION_NAME = "gen_ai.operation.name"
OUTPUT_MESSAGES = "gen_ai.output.messages"
OUTPUT_TYPE = "gen_ai.output.type"
PROMPT_NAME = "gen_ai.prompt.name"
PROVIDER_NAME = "gen_ai.provider.name"
REQUEST_CHOICE_COUNT = "gen_ai.request.choice.count"
REQUEST_ENCODING_FORMATS = "gen_ai.request.encoding_formats"
REQUEST_FREQUENCY_PENALTY = "gen_ai.request.frequency_penalty"
REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
REQUEST_MODEL = "gen_ai.request.model"
REQUEST_PRESENCE_PENALTY = "gen_ai.request.presence_penalty"
REQUEST_SEED = "gen_ai.request.seed"
REQUEST_STOP_SEQUENCES = "gen_ai.request.stop_sequences"
REQUEST_STREAM = "gen_ai.request.stream"
REQUEST_TEMPERATURE = "gen_ai.request.temperature"
REQUEST_TOP_K = "gen_ai.request.top_k"
REQUEST_TOP_P = "gen_ai.request.top_p"
RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
RESPONSE_ID = "gen_ai.response.id"
RESPONSE_MODEL = "gen_ai.response.model"
RESPONSE_TIME_TO_FIRST_CHUNK = "gen_ai.response.time_to_first_chunk"
RETRIEVAL_DOCUMENTS = "gen_ai.retrieval.documents"
RETRIEVAL_QUERY_TEXT = "gen_ai.retrieval.query.text"
SYSTEM_INSTRUCTIONS = "gen_ai.system_instructions"
TOKEN_TYPE = "gen_ai.token.type"
TOOL_CALL_ARGUMENTS = "gen_ai.tool.call.arguments"
TOOL_CALL_ID = "gen_ai.tool.call.id"
TOOL_CALL_RESULT = "gen_ai.tool.call.result"
TOOL_DEFINITIONS = "gen_ai.tool.definitions"
TOOL_DESCRIPTION = "gen_ai.tool.description"
TOOL_NAME = "gen_ai.tool.name"
TOOL_TYPE = "gen_ai.tool.type"
USAGE_CACHE_CREATION_INPUT_TOKENS = "gen_ai.usage.cache_creation.input_tokens"
USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"
USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
USAGE_REASONING_OUTPUT_TOKENS = "gen_ai.usage.reasoning.output_tokens"
WORKFLOW_NAME = "gen_ai.workflow.name"
SERVER_ADDRESS = "server.address"

# --- Métricas ---
OPERATION_DURATION = "gen_ai.client.operation.duration"
OPERATION_TIME_PER_OUTPUT_CHUNK = "gen_ai.client.operation.time_per_output_chunk"
OPERATION_TIME_TO_FIRST_CHUNK = "gen_ai.client.operation.time_to_first_chunk"
TOKEN_USAGE = "gen_ai.client.token.usage"
SERVER_REQUEST_DURATION = "gen_ai.server.request.duration"
SERVER_TIME_PER_OUTPUT_TOKEN = "gen_ai.server.time_per_output_token"
SERVER_TIME_TO_FIRST_TOKEN = "gen_ai.server.time_to_first_token"

# Tipo declarado por el modelo, para que el traductor pueda validar lo que emite.
ATTRIBUTE_TYPES: dict[str, str] = {
    "error.type": "enum",
    "gen_ai.agent.description": "string",
    "gen_ai.agent.id": "string",
    "gen_ai.agent.name": "string",
    "gen_ai.agent.version": "string",
    "gen_ai.conversation.id": "string",
    "gen_ai.data_source.id": "string",
    "gen_ai.embeddings.dimension.count": "int",
    "gen_ai.evaluation.explanation": "string",
    "gen_ai.evaluation.name": "string",
    "gen_ai.evaluation.score.label": "string",
    "gen_ai.evaluation.score.value": "double",
    "gen_ai.input.messages": "any",
    "gen_ai.operation.name": "enum",
    "gen_ai.output.messages": "any",
    "gen_ai.output.type": "enum",
    "gen_ai.prompt.name": "string",
    "gen_ai.provider.name": "enum",
    "gen_ai.request.choice.count": "int",
    "gen_ai.request.encoding_formats": "string[]",
    "gen_ai.request.frequency_penalty": "double",
    "gen_ai.request.max_tokens": "int",
    "gen_ai.request.model": "string",
    "gen_ai.request.presence_penalty": "double",
    "gen_ai.request.seed": "int",
    "gen_ai.request.stop_sequences": "string[]",
    "gen_ai.request.stream": "boolean",
    "gen_ai.request.temperature": "double",
    "gen_ai.request.top_k": "double",
    "gen_ai.request.top_p": "double",
    "gen_ai.response.finish_reasons": "string[]",
    "gen_ai.response.id": "string",
    "gen_ai.response.model": "string",
    "gen_ai.response.time_to_first_chunk": "double",
    "gen_ai.retrieval.documents": "any",
    "gen_ai.retrieval.query.text": "string",
    "gen_ai.system_instructions": "any",
    "gen_ai.token.type": "enum",
    "gen_ai.tool.call.arguments": "any",
    "gen_ai.tool.call.id": "string",
    "gen_ai.tool.call.result": "any",
    "gen_ai.tool.definitions": "any",
    "gen_ai.tool.description": "string",
    "gen_ai.tool.name": "string",
    "gen_ai.tool.type": "string",
    "gen_ai.usage.cache_creation.input_tokens": "int",
    "gen_ai.usage.cache_read.input_tokens": "int",
    "gen_ai.usage.input_tokens": "int",
    "gen_ai.usage.output_tokens": "int",
    "gen_ai.usage.reasoning.output_tokens": "int",
    "gen_ai.workflow.name": "string",
    "server.address": "string",
}

METRIC_UNITS: dict[str, str] = {
    "gen_ai.client.operation.duration": "s",
    "gen_ai.client.operation.time_per_output_chunk": "s",
    "gen_ai.client.operation.time_to_first_chunk": "s",
    "gen_ai.client.token.usage": "{token}",
    "gen_ai.server.request.duration": "s",
    "gen_ai.server.time_per_output_token": "s",
    "gen_ai.server.time_to_first_token": "s",
}
