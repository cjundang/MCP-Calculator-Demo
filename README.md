# MCP Math Demo (LLM-routed, 4 servers)

โปรแกรม Demo MCP ที่แยก server เป็น 4 ตัว ตัวละ 1 การคำนวณ และใช้ LLM ผ่าน
**OpenRouter** เป็นตัวแยกวิเคราะห์ข้อความและเลือกว่าจะเรียก server/tool ตัวไหน
(แทนการ parse ด้วย regex/keyword แบบเดิม)

## โครงสร้าง

แต่ละ server รันเป็นบริการบนเครือข่ายผ่าน **TCP** (transport `streamable-http`)
คนละพอร์ต:

```
servers/
  add_server.py       -> MCP server #1, tool: add       -> TCP 127.0.0.1:8001/mcp
  subtract_server.py  -> MCP server #2, tool: subtract  -> TCP 127.0.0.1:8002/mcp
  multiply_server.py  -> MCP server #3, tool: multiply  -> TCP 127.0.0.1:8003/mcp
  divide_server.py    -> MCP server #4, tool: divide    -> TCP 127.0.0.1:8004/mcp
start_servers.py      -> สคริปต์ช่วยสตาร์ท server ทั้ง 4 ตัวพร้อมกัน
client.py             -> เชื่อมต่อทั้ง 4 server ผ่าน TCP + ใช้ OpenRouter เลือก tool
.env                  -> OPENROUTER_KEY (อย่า commit ขึ้น git)
```

เปลี่ยนพอร์ต/โฮสต์ได้ผ่าน env: `MCP_HOST`, `ADD_PORT`, `SUBTRACT_PORT`,
`MULTIPLY_PORT`, `DIVIDE_PORT` (ทั้ง server และ client อ่านค่าชุดเดียวกัน)

## การเลือก server ทำงานอย่างไร

เนื่องจากแต่ละ tool อยู่คนละ server การ "เลือก tool" = การ "เลือก server"
ลำดับการทำงานของ client:

1. spawn ทั้ง 4 server ผ่าน stdio แล้ว `list_tools()` ของแต่ละตัว
2. รวม tool ทั้งหมดเป็น OpenAI "tools" schema พร้อมจำว่าแต่ละ tool อยู่ server ไหน
3. ส่งข้อความผู้ใช้ + schema ไปที่ LLM ผ่าน OpenRouter (`tool_choice="required"`)
4. LLM ตัดสินใจเรียก tool ไหน พร้อมค่า `a`, `b` — **ขั้นตอนนี้คือการเลือก server**
5. client route คำเรียกไปยัง server เจ้าของ tool นั้น แล้วคืนผลลัพธ์

client จะพิมพ์ให้เห็นว่าเลือก tool ใด route ไป server ใด และใช้ argument อะไร

```
> 12 + 3
  LLM selected tool : add
  routed to server  : add-server
  arguments         : {'a': 12, 'b': 3}
  result            : 15.0
```

## การติดตั้ง

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## LLM Provider (Ollama เป็นหลัก, OpenRouter เป็น fallback)

client จะเลือกผู้ให้บริการ LLM ตามลำดับ:

1. **Ollama ในเครื่อง (หลัก)** — ถ้าเชื่อมต่อ `http://localhost:11434/v1` ได้ จะใช้โมเดล
   Qwen (`qwen3:8b`) ในเครื่อง ไม่ต้องใช้อินเทอร์เน็ตและไม่มีค่าใช้จ่าย
2. **OpenRouter (สำรอง)** — ถ้าเชื่อมต่อ Ollama ไม่ได้ จะสลับไปใช้ OpenRouter อัตโนมัติ
   (ต้องมี `OPENROUTER_KEY`)

client จะพิมพ์บอกว่ากำลังใช้ provider ไหน เช่น `Using LLM provider: ollama (qwen3:8b)`

### การตั้งค่าทั้งหมดอยู่ใน `.env`

ค่าที่ปรับได้ทุกตัวรวมศูนย์ไว้ใน `.env` และโหลดผ่าน `config.py` (single source of
truth) โค้ดทุกไฟล์ (`client.py`, `servers/*.py`, `start_servers.py`) อ่านค่าจากที่นี่

```
# LLM หลัก: Ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen3:8b
OLLAMA_PROBE_TIMEOUT=2.0

# LLM สำรอง: OpenRouter
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_KEY=sk-or-v1-...

# MCP servers (TCP / streamable-http)
MCP_HOST=127.0.0.1
MCP_TRANSPORT=streamable-http
MCP_HTTP_PATH=/mcp
ADD_PORT=8001
SUBTRACT_PORT=8002
MULTIPLY_PORT=8003
DIVIDE_PORT=8004

# อื่น ๆ
SERVER_SHUTDOWN_TIMEOUT=5
DEBUG=
SYSTEM_PROMPT=You are a calculator router. ...
```

แก้ค่าใน `.env` แล้วมีผลทันทีกับทั้ง server และ client โดยไม่ต้องแก้โค้ด

ต้องมี Ollama ติดตั้งและดึงโมเดล Qwen ไว้ก่อน:

```bash
ollama pull qwen3:8b
# ollama serve   # ปกติรันเป็น service อยู่แล้ว
```

## การใช้งาน

**ขั้นที่ 1** — สตาร์ท server ทั้ง 4 ตัว (รันค้างไว้ในเทอร์มินัลหนึ่ง):

```bash
python start_servers.py
```

หรือสตาร์ททีละตัวคนละเทอร์มินัลก็ได้:

```bash
python servers/add_server.py --port 8001
python servers/subtract_server.py --port 8002
python servers/multiply_server.py --port 8003
python servers/divide_server.py --port 8004
```

**ขั้นที่ 2** — รัน client (อีกเทอร์มินัลหนึ่ง):

```bash
python client.py "12 + 3"
python client.py "หาผลบวกของ 5 และ 7"
python client.py "20 หาร 5"
python client.py            # โหมดโต้ตอบ; พิมพ์ exit เพื่อออก
```

## ผลการทดสอบ (สรุปการเลือก server)

| ข้อความ | tool ที่เลือก | server | ผลลัพธ์ |
|---------|--------------|--------|---------|
| `12 + 3` | add | add-server | 15.0 |
| `หาผลบวกของ 5 และ 7` | add | add-server | 12.0 |
| `เอา 50 ลบ 8` | subtract | subtract-server | 42.0 |
| `10 คูณ 4` | multiply | multiply-server | 40.0 |
| `8 x 6` | multiply | multiply-server | 48.0 |
| `20 หาร 5` | divide | divide-server | 4.0 |
| `100 minus 45` | subtract | subtract-server | 55.0 |
| `9 หาร 0` | divide | divide-server | ERROR (หารด้วยศูนย์) |

## หมายเหตุด้านความปลอดภัย

`.env` มี API key อยู่ ควรเพิ่มไว้ใน `.gitignore` (ทำให้แล้ว) และถ้าเคยแชร์ key
ออกไป แนะนำให้ rotate key ใหม่บน OpenRouter
