# Server-Sent Events (SSE) Protocol Contract (`POST /api/v1/chat/stream`)

## Overview
When the client (Laravel Livewire / Alpine.js) opens a connection to `/api/v1/chat/stream`, FastAPI streams structured SSE events to enable a real-time, responsive typing animation for humanized responses, followed by execution metadata and the dataset token for the Excel download button.

---

## Event Types

### 1. `event: session`
Emitted immediately once the session is initialized or resolved.

```text
event: session
data: {"session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d", "status": "processing"}
```

---

### 2. `event: token`
Emitted repeatedly as the local LLM generates conversational text tokens. The client appends each `text` chunk to the active message container.

```text
event: token
data: {"text": "Actualmente, "}

event: token
data: {"text": "se registran "}

event: token
data: {"text": "5 órdenes con demoras críticas en el proceso de corte."}
```

---

### 3. `event: query_info` (Optional)
Emitted when a database query was executed against MariaDB, providing transparency.

```text
event: query_info
data: {"intent": "data_query", "sql": "SELECT id_orden, codigo_proceso, horas_retraso FROM ordenes_proceso WHERE horas_retraso > 0 ORDER BY horas_retraso DESC LIMIT 5;"}
```

---

### 4. `event: dataset` (Conditional)
Emitted if the response generated tabular records suitable for Excel export. This informs the Laravel frontend to render the `[ 📊 Generar Excel ]` button.

```text
event: dataset
data: {"dataset_id": "ds_a8b9c0d1e2f3", "row_count": 5, "columns": ["id_orden", "codigo_proceso", "horas_retraso"]}
```

---

### 5. `event: done`
Emitted at the end of the stream, carrying summary performance metrics.

```text
event: done
data: {"status": "completed", "total_tokens": 128, "latency_ms": 1150}
```

---

### 6. `event: error`
Emitted if an unhandled exception or SQL parsing violation occurs during the stream.

```text
event: error
data: {"code": "SQL_GUARDRAIL_VIOLATION", "detail": "La consulta solicitada no cumple con las políticas de solo lectura."}
```

---

## Client-Side Integration Example (Alpine.js / JavaScript)

```javascript
async function sendStreamMessage(prompt, sessionId) {
  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + apiToken,
      'Accept': 'text/event-stream'
    },
    body: JSON.stringify({ prompt, session_id: sessionId })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n\n');
    buffer = lines.pop(); // keep remainder

    for (const block of lines) {
      const eventMatch = block.match(/^event:\s*(\w+)/m);
      const dataMatch = block.match(/^data:\s*(.+)$/m);
      if (!eventMatch || !dataMatch) continue;

      const event = eventMatch[1];
      const payload = JSON.parse(dataMatch[1]);

      if (event === 'token') {
        activeMessage.text += payload.text;
      } else if (event === 'dataset') {
        activeMessage.hasExcel = true;
        activeMessage.datasetId = payload.dataset_id;
      }
    }
  }
}
```