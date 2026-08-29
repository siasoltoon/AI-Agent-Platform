# AI Agent Platform — Final Production Acceptance

## هدف

این سند معیار نهایی آماده‌بودن پلتفرم برای دریافت Taskهای واقعی پروژه‌هاست. موفقیت فقط به معنی سبز بودن unit testها نیست؛ مسیر واقعی Controller → Task Store → Task Runner → Worker → Agent Executor → Tools → Evidence نیز باید سالم باشد.

## قرارداد نهایی

- Taskها قبل از اجرا در SQLite پایدار ذخیره می‌شوند.
- Task Runner پس از restart، Taskهای `running` را از مسیر recovery به `queued` برمی‌گرداند.
- `running → queued` در lifecycle معتبر است، ولی از API عمومی update قابل سوءاستفاده نیست.
- وضعیت‌های `completed`، `failed` و `cancelled` پایانی هستند.
- Task با شناسه تکراری پذیرفته نمی‌شود.
- لغو Task authoritative است و نتیجه دیررس Worker نباید آن را دوباره completed کند.
- completion بدون `execution_evidence.verified == true` معتبر نیست.
- completion بدون حداقل یک tool action موفق معتبر نیست.
- برای عملیات فایل، evidence باید وضعیت واقعی filesystem را نشان دهد.
- برای Taskهای دارای درخواست verification، صرفاً ادعای مدل کافی نیست و باید read/verification واقعی انجام شود.
- خروجی، timeout، تعداد step و metadata دارای سقف هستند.
- Worker ورودی‌های prompt/model/timeout/metadata را validate می‌کند.
- Worker خطای validation/execution را با HTTP status مناسب برمی‌گرداند و controller آن را به failed تبدیل می‌کند.
- ابزارهای filesystem مسیر را داخل workspace نگه می‌دارند.
- Terminal دارای allowlist و blocked-operation guard است.
- Git و toolchainهای توسعه برای عملیات واقعی در Worker در دسترس هستند.
- Dashboard از endpointهای task و agent status استفاده می‌کند و CORS صریح است.

## مسیر عملیاتی نهایی

```text
Dashboard
   ↓
FastAPI Controller
   ↓
Task Contract + Validation
   ↓
SQLite Task Store
   ↓
Task Runner / Claim / Recovery / Cancellation
   ↓
Agent Runtime
   ↓
PC Worker
   ↓
Ollama
   ↓
Agent Executor
   ↓
Tool Registry
   ├── filesystem tools
   └── controlled terminal/toolchain
   ↓
Observable execution
   ↓
Verification / Evidence
   ↓
TaskStore terminal state
   ↓
Dashboard
```

## Gateهای اجباری

1. `python -m pytest -q`
2. `python -m py_compile agent_core\\execution_agent.py agent_core\\runtime.py backend\\main.py backend\\task_runner.py worker_system\\worker.py`
3. `python scripts/production_gate.py`
4. Worker health روی پورت configured پاسخ معتبر بدهد.
5. یک Task واقعی از Dashboard ثبت شود و در Store `queued → running → completed/failed` حرکت کند.
6. Task ساخت فایل باید واقعاً فایل را ایجاد، بخواند و محتوای دقیق را verify کند.
7. Task دارای failure باید `failed` و خطای واقعی داشته باشد؛ هرگز با متن مدل completed نشود.
8. restart Worker/Controller نباید Taskهای running را گم کند.
9. cancellation نباید با completion دیررس Worker overwrite شود.
10. Task ID تکراری باید reject شود.

## Definition of Done

پلتفرم زمانی برای دریافت Taskهای پروژه‌های واقعی آماده محسوب می‌شود که تمام gateهای بالا سبز باشند و هیچ failure شناخته‌شده‌ای در مسیر اجرای واقعی باقی نمانده باشد.

این پروژه برای اجرای Taskهای واقعی coding/development طراحی شده است؛ آماده‌بودن به معنی تضمین کیفیت کد تولیدشده توسط مدل نیست. هر Task واقعی همچنان باید بر اساس evidence و نتیجه ابزارها تصمیم‌گیری شود.
