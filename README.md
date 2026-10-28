# payment-processing

Микросервис асинхронной обработки платежей. Принимает платёж, проводит его через эмуляцию платёжного шлюза и сообщает результат на webhook клиента.

Стек: FastAPI, Pydantic v2, SQLAlchemy 2 (async), PostgreSQL, Alembic, RabbitMQ (FastStream), Docker.

## Как это работает

```
POST /api/v1/payments
   │  одна транзакция: INSERT payments + INSERT outbox
   ▼
outbox ──relay (в процессе api, раз в 1 с)──▶ exchange "payments" ──▶ queue "payments.process"
                                                                           │
                                                                       consumer
                                                       шлюз (2–5 с, 90% успех) → статус в БД → webhook
                                                                           │ ошибка
                                     ┌─────────────────────────────────────┤
                                     ▼ попытка 1, 2                        ▼ попытка 3
                     payments.process.retry.2s / .4s          reject → "payments.dlx" → payments.process.dlq
                     (TTL, потом обратно в "payments")
```

**Outbox.** Платёж и событие `payment.created` пишутся в одной транзакции, поэтому событие не теряется, даже если брокер в этот момент лежит. Relay забирает неопубликованные события через `SELECT … FOR UPDATE SKIP LOCKED`, публикует их с подтверждением брокера (persistent) и только потом ставит `published_at`. Несколько экземпляров api не публикуют одно событие дважды.

**Идемпотентность API.** Заголовок `Idempotency-Key` обязателен. Вставка идёт через `INSERT … ON CONFLICT DO NOTHING` по уникальному ключу, так что даже одновременные запросы с одним ключом создают один платёж и одно событие. Повторный запрос возвращает исходный платёж (202, тот же `payment_id`).

**Идемпотентность consumer'а.** Доставка at-least-once, дубли возможны. Шлюз вызывается только для платежа в статусе `pending`, а смена статуса делается одним `UPDATE … WHERE status = 'pending'`. Ретрай после упавшего webhook не списывает деньги второй раз.

**Retry и DLQ.** Любая ошибка обработки (чаще всего недоступный webhook) переотправляет сообщение в очередь задержки: перед 2-й попыткой ждём 2 с, перед 3-й — 4 с. Номер попытки едет в заголовке `x-attempt`. Под каждую задержку своя очередь с `x-message-ttl`: по истечении TTL сообщение через dead-letter возвращается в основной exchange. После 3-й неудачи сообщение отклоняется без requeue, и RabbitMQ по `x-dead-letter-exchange` кладёт его в `payments.process.dlq`.

## Запуск

```bash
cp .env.example .env      # заполнить логины, пароли и API_KEY
docker compose up -d --build
```

Сервисы: `db` (PostgreSQL), `rabbitmq` (management UI на http://localhost:15672), `api` (http://localhost:8000, Swagger на `/docs`), `consumer`. Миграции применяет `api` при старте.

Postgres читает `POSTGRES_*` только при первом создании volume, поэтому после смены `DB_USER` или `DB_PASS` нужен `docker compose down -v`.

## Примеры

Все запросы требуют заголовок `X-API-Key` со значением `API_KEY` из `.env`.

Создание платежа:

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: order-42" \
  -H "Content-Type: application/json" \
  -d '{
        "amount": "1500.00",
        "currency": "RUB",
        "description": "Order 42",
        "metadata": {"order_id": 42},
        "webhook_url": "https://webhook.site/your-id"
      }'
```

```json
HTTP/1.1 202 Accepted
{"payment_id": "f81e37dc-03fe-4598-acb5-d24885a912ca", "status": "pending", "created_at": "2026-10-28T09:24:29.289340Z"}
```

Получение платежа:

```bash
curl http://localhost:8000/api/v1/payments/f81e37dc-03fe-4598-acb5-d24885a912ca -H "X-API-Key: $API_KEY"
```

```json
{
  "payment_id": "f81e37dc-03fe-4598-acb5-d24885a912ca",
  "amount": "1500.00",
  "currency": "RUB",
  "description": "Order 42",
  "metadata": {"order_id": 42},
  "status": "succeeded",
  "idempotency_key": "order-42",
  "webhook_url": "https://webhook.site/your-id",
  "created_at": "2026-10-28T09:24:29.289340Z",
  "processed_at": "2026-10-28T09:24:31.415051Z"
}
```

Webhook приходит `POST`-запросом с тем же телом, что у `GET /api/v1/payments/{payment_id}`. Доставленным считается любой ответ 2xx.

Ошибки: `401` — нет или неверный `X-API-Key`, `404` — платежа нет, `422` — ошибка валидации (нет `Idempotency-Key`, валюта не из RUB/USD/EUR, `amount <= 0`, невалидный URL).

Посмотреть путь в DLQ: создать платёж с `webhook_url`, который отвечает 5xx. В логах consumer'а будут три попытки с паузами 2 и 4 с, а сообщение окажется в `payments.process.dlq`:

```bash
docker compose logs -f consumer
docker compose exec rabbitmq rabbitmqctl list_queues name messages
```

## Тесты

Тесты идут в настоящий PostgreSQL, потому что корректность держат `ON CONFLICT` и `SKIP LOCKED`, которых в SQLite нет. База `payments_test` отдельная и создаётся автоматически.

```bash
docker compose up -d db
pip install -r requirements-dev.txt
pytest
```

## Структура

```
app/
├── settings.py, database.py, logger.py, enums.py, security.py
├── main.py              # FastAPI + lifespan с outbox relay
├── consumer.py          # FastStream-приложение: обработчик, retry, DLQ
├── broker.py            # брокер и топология RabbitMQ
├── dao/base.py
├── payment/             # models, schemas, dao, dependencies, router
├── outbox/              # models, dao, relay
├── gateway/client.py    # эмуляция платёжного шлюза
├── webhook/             # HTTP-клиент webhook'ов и его исключения
├── services/            # создание платежа (payment + outbox), обработка в consumer'е
└── migrations/
```

## Принятые решения

- 10% «ошибок» шлюза — это бизнес-результат: платёж получает статус `failed`, клиент получает webhook. Retry касается технических сбоев, а не отказа в оплате.
- При повторе с тем же `Idempotency-Key` тело запроса с исходным не сравнивается: возвращается исходный платёж.
- Webhook доставляется at-least-once: если ответ клиента потерялся, он может прийти повторно. Получатель дедуплицирует по `payment_id`.
- Relay запущен в процессе api, отдельный сервис под него не нужен. `SKIP LOCKED` позволяет держать несколько реплик api.
