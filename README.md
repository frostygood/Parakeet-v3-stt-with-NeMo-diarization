# STT API - Speech-to-Text Service

Сервис транскрибации аудио и видео с использованием Parakeet v3 и разделением на спикеров (diarization).

## Архитектура

- **FastAPI** - REST API + фоновые задачи
- **Parakeet v3 (HuggingFace)** - транскрибация речи
- **Pyannote.audio** - разделение на спикеров
- **Docker Compose** - контейнеризация

## Быстрый старт (Docker)

1. Клонируйте репозиторий:
```bash
git clone <repo-url>
cd stt-api
```

2. Создайте .env файл с токеном и API ключом:
```bash
# Отредактируйте .env и добавьте ваш HuggingFace токен и API_KEY
```

3. Запустите сервис:
```bash
docker-compose up --build
```

4. Откройте в браузере: http://localhost:4787

## HuggingFace Token

Для работы сервиса необходим токен HuggingFace:

1. Зарегистрируйтесь на https://huggingface.co
2. Получите токен: https://huggingface.co/settings/tokens
3. Для pyannote.audio необходимо принять лицензию:
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0

## Docker Compose

### Запуск:
```bash
# Первый запуск (сборка образа)
docker-compose up --build

# Обычный запуск
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Остановка
docker-compose down

# Полный сброс (с удалением volumes)
docker-compose down -v
```

### Сервисы:
- **api** (порт 4787) - FastAPI приложение

### Health Checks:
- API: `GET /health`

## API Endpoints

### 1. GET /health
Health check endpoint для мониторинга.

**Response:**
```json
{
  "status": "healthy",
  "service": "stt-api",
  "version": "1.0.0"
}
```

### 2. POST /transcribe
Загрузить файл и начать транскрибацию (с валидацией)

```bash
POST /transcribe
Content-Type: multipart/form-data

file: file (required)
enable_diarization: bool - optional, default: false
```

По умолчанию сервис делает:
- сырую транскрибацию
- разбивку по словам с таймкодами
- умную сегментацию для SRT
- разбивку на спикеров с таймкодами (если enable_diarization=true)

**Response:**
```json
{
  "task_id": "uuid",
  "status": "pending",
  "message": "Transcription task started",
  "result_url": "/result/{task_id}"
}
```

**Errors:**
- `413 Payload Too Large` - Файл превышает 500MB
- `400 Bad Request` - Недопустимый тип файла

### 3. GET /status/{task_id}
Проверить статус задачи

**Response (pending/processing):**
```json
{
  "task_id": "uuid",
  "status": "pending|processing",
  "progress": 50,
  "step": "Extracting audio from video"
}
```

**Response (completed):**
```json
{
  "task_id": "uuid",
  "status": "completed",
  "result_url": "/result/{task_id}",
  "raw_text": "transcribed text...",
  "words": [{"word": "hello", "start": 0.12, "end": 0.42}],
  "srt": "1\n00:00:00,120 --> 00:00:01,400\nhello\n",
  "speaker_srt": "1\n00:00:00,120 --> 00:00:01,400\nSPEAKER_00: hello\n",
  "srt_segments": [{"start": 0.12, "end": 1.4, "text": "hello"}],
  "speaker_segments": [{"start": 0.12, "end": 1.4, "speaker": "SPEAKER_00", "text": "hello"}],
  "processing_time": 45.2,
  "duration": 120.5
}
```

### 4. GET /result/{task_id}
Скачать JSON с результатом (все варианты сразу)

### 5. GET /
Web интерфейс

## Безопасность

- ✅ Проверка API ключа через заголовок `X-API-Key`
- ✅ Для всех API запросов требуется `X-API-Key`, кроме `/health` и статических файлов
- ✅ Валидация размера файла (максимум 500MB)
- ✅ Валидация типа файла (только аудио/видео)
- ✅ Санитайзинг filename (защита от path traversal)
- ✅ Автоматическое удаление временных файлов
- ⚠️  .env в .gitignore (но обязательно использовать уникальные токены)

## Пример использования cURL

```bash
# Загрузить файл и начать транскрибацию
curl -X POST http://localhost:4787/transcribe \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@audio.mp3" \
  -F "enable_diarization=true"

# Проверить статус (когда completed вернёт text)
curl http://localhost:4787/status/{task_id}

# Скачать результат
curl http://localhost:4787/result/{task_id} -o result.txt
```

## Структура проекта

```
stt-api/
├── app/
│   ├── __init__.py
│   ├── constants.py         # Константы приложения
│   ├── logging_config.py   # Конфигурация логирования
│   ├── main.py            # FastAPI endpoints
│   ├── config.py          # Settings
│   ├── utils.py           # Utility functions
│   ├── task_store.py      # In-memory task state
│   └── models.py         # Pydantic models
├── services/
│   ├── transcription.py   # Parakeet v3 (HuggingFace)
│   ├── diarization.py     # Pyannote.audio
│   └── audio_processor.py # FFmpeg wrapper
├── tasks/
│   └── transcription_task.py # Background tasks
├── static/
│   └── index.html          # Web UI
├── uploads/               # Temp uploads (auto-delete)
├── transcriptions/        # Results storage
├── models/                # Model cache
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Разработка (без Docker)

1. Создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Установите FFmpeg:
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg
```

4. Запустите сервис:
```bash
# FastAPI
python -m app.main
```

## Логирование

Приложение использует стандартное Python логирование:
- Уровень логирования настраивается через переменные окружения
- Структурированный формат: `TIMESTAMP - MODULE - LEVEL - MESSAGE`
- Transformers/PyTorch логи: WARNING уровень (для уменьшения шума)

## Особенности

- ✅ Единый API endpoint для загрузки и транскрибации
- ✅ Валидация размера и типа файла
- ✅ Санитайзинг filename (защита от path traversal)
- ✅ Автоматическое удаление файлов после обработки
- ✅ Поддержка аудио и видео форматов
- ✅ Разделение на спикеров (diarization)
- ✅ Генерация субтитров (SRT)
- ✅ CPU-only режим
- ✅ Web интерфейс
- ✅ Docker Compose для простого развертывания
- ✅ Health check для API
- ✅ Структурированное логирование
- ⚠️ Статус задач хранится в памяти и сбрасывается при перезапуске

## Лицензия

MIT
