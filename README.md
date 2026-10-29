# Physical Chatbot Trigger

> A cloud-based alert notification system that sends real-time messages to a Discord channel through a fully serverless AWS backend.

---

## Abstract

Physical Chatbot Trigger is a cloud computing project that demonstrates how a web-based interface can trigger serverless functions on AWS to deliver real-time notifications. A user enters an alert message in a browser-based dashboard and clicks **Send Alert**. The message travels through Amazon API Gateway to an AWS Lambda function, which stores the event in DynamoDB and forwards the message to a Discord channel using a webhook. The entire architecture uses only managed, pay-per-use services — there is no server to provision, patch, or scale.

---

## Problem Statement

In many environments — laboratories, classrooms, event venues — there is a need to quickly broadcast alerts to a team or monitoring channel. Physical button systems exist, but they require hardware, firmware, and physical installation. This project replaces the hardware button with a web interface and uses cloud services to deliver alerts reliably, securely, and at near-zero cost.

---

## Objectives

1. Build a professional, mobile-friendly web dashboard for sending alerts.
2. Route messages securely through a serverless AWS backend.
3. Store every alert in a cloud database with timestamp and delivery status.
4. Deliver alerts to Discord in real time using webhooks.
5. Never expose secrets (Discord webhook URL, AWS credentials) in frontend code.
6. Demonstrate AWS free-tier deployment suitable for a college project budget.

---

## Software and AWS Services Used

| Layer | Technology |
|-------|-----------|
| Frontend | HTML5, CSS3 (Vanilla), JavaScript (ES2022) |
| Hosting | Amazon S3 Static Website Hosting |
| API | Amazon API Gateway (REST, Regional) |
| Backend Logic | AWS Lambda (Python 3.12) |
| Database | Amazon DynamoDB (On-Demand) |
| Secret Management | AWS Secrets Manager |
| Logging | Amazon CloudWatch Logs |
| Notifications | Discord Webhook |
| Development | Visual Studio Code, AWS CLI v2 |
| Version Control | Git + GitHub |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        USER BROWSER                         │
│   S3-hosted HTML/CSS/JS dashboard                           │
│   Physical Chatbot Trigger — "Send Alert" button            │
└────────────────────────────┬────────────────────────────────┘
                             │  HTTPS POST /alert
                             ▼
┌─────────────────────────────────────────────────────────────┐
│               AMAZON API GATEWAY (REST)                     │
│   - Request validation & throttling (10 req/s)              │
│   - CORS configuration                                      │
│   - Lambda Proxy Integration                                │
└────────────────────────────┬────────────────────────────────┘
                             │  Event (JSON)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│               AWS LAMBDA — Python 3.12                      │
│   1. Validate message (length, content)                     │
│   2. Write record to DynamoDB (status = pending)            │
│   3. Fetch Discord webhook from Secrets Manager             │
│   4. POST rich embed to Discord                             │
│   5. Update DynamoDB record (status = delivered/failed)     │
│   6. Return JSON response to API Gateway                    │
└──────────────┬─────────────────────────┬───────────────────┘
               │                         │
               ▼                         ▼
┌─────────────────────┐     ┌──────────────────────────────┐
│  AMAZON DYNAMODB    │     │  DISCORD WEBHOOK             │
│  Table: ChatbotAlerts│    │  #alerts channel             │
│  - alertId (PK)     │     │  Rich embed with:            │
│  - timestamp        │     │  • Message text              │
│  - message          │     │  • Sender name               │
│  - sender           │     │  • Alert ID                  │
│  - status           │     │  • Timestamp                 │
└─────────────────────┘     └──────────────────────────────┘
               │
               ▼
┌─────────────────────┐
│  AMAZON CLOUDWATCH  │
│  Lambda execution   │
│  logs & metrics     │
└─────────────────────┘
```

---

## Workflow

1. **User opens website** → Browser loads from S3 static hosting
2. **User types message** → Frontend validates length (max 500 chars)
3. **User clicks Send Alert** → `fetch()` POSTs JSON to API Gateway endpoint
4. **API Gateway** → Validates request, triggers Lambda with proxy event
5. **Lambda** → Parses body, validates input, generates UUID
6. **Lambda → DynamoDB** → Stores alert with `status: pending`
7. **Lambda → Secrets Manager** → Retrieves Discord webhook URL (cached in memory)
8. **Lambda → Discord** → POSTs rich embed message via webhook
9. **Lambda → DynamoDB** → Updates `status: delivered` or `status: failed`
10. **Lambda → API Gateway → Browser** → Returns `{alertId, discordStatus}`
11. **Frontend** → Shows success/error toast, updates history panel and stats

---

## Main Features

### Frontend
- ✅ Dark-mode glassmorphism UI with gradient accents
- ✅ Three one-click preset buttons (Help Required, Emergency Alert, System Notification)
- ✅ Custom message textarea with character counter (0/500)
- ✅ Real-time input validation with error messages
- ✅ Loading spinner during API call
- ✅ Success/error toast notifications
- ✅ Session stats (Total / Success / Failed counters)
- ✅ Recent alert history panel with status badges
- ✅ Architecture diagram built into the dashboard
- ✅ Live API status indicator (Online / Offline)
- ✅ Fully responsive — works on phone, tablet, and desktop

### Backend (Lambda)
- ✅ Input validation (required field, max length, type check)
- ✅ CORS pre-flight handling
- ✅ UUID-based alert IDs
- ✅ DynamoDB write with automatic status update
- ✅ Discord webhook with rich embed (colour-coded by alert type)
- ✅ Secrets Manager integration (webhook URL never in code)
- ✅ Structured CloudWatch logging
- ✅ Graceful error handling (Discord failure does not break the response)

---

## Testing Procedure

### Local Unit Tests

```bash
cd "c:\code\demo cloud"
pip install pytest
pytest tests/ -v
```

Expected output: 17 tests passing.

### Manual API Test (PowerShell)

```powershell
Invoke-RestMethod `
  -Uri "https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod/alert" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"message":"Manual test","sender":"Viva Demo"}'
```

### Lambda Console Test

Use the test event in the Lambda console (see deployment guide Step 7.5).

### End-to-End Test

Open the S3 website URL → Send an alert → Verify Discord message + DynamoDB record.

---

## Advantages

| Advantage | Details |
|-----------|---------|
| **Serverless** | No server management, patching, or scaling required |
| **Cost-effective** | Near-zero cost within AWS free tier |
| **Secure** | Secrets never in frontend; least-privilege IAM |
| **Scalable** | Handles spikes automatically — Lambda scales to 1000 concurrent executions |
| **Fast** | Lambda cold-start < 500ms; warm invocations < 100ms |
| **Observable** | Every invocation logged to CloudWatch |
| **Portable** | Any browser, any device, any OS |

---

## Limitations

| Limitation | Reason |
|-----------|--------|
| No real-time history sync | History stored in browser memory only; refreshing loses session history |
| Discord-only notifications | Only one notification channel supported |
| No authentication | Any person with the URL can send alerts |
| No rate limiting on frontend | Throttling is applied at API Gateway, not in UI |
| S3 HTTP only | S3 static hosting does not serve HTTPS by default (requires CloudFront) |

---

## Future Enhancements

1. **CloudFront + HTTPS** — Add a CloudFront distribution in front of S3 for secure HTTPS hosting.
2. **User Authentication** — Add AWS Cognito to require login before sending alerts.
3. **Real-time History** — Use DynamoDB Streams + WebSocket API Gateway to push new alerts to the browser in real time.
4. **Multiple Channels** — Allow users to choose between Discord, Slack, Email (SES), or SMS (SNS).
5. **Alert Categories** — Add severity levels and filter history by category.
6. **Mobile App** — Build a React Native version using AWS Amplify.
7. **IoT Integration** — Reconnect the original ESP32 hardware button to the same API endpoint.
8. **Analytics Dashboard** — Use Amazon QuickSight to visualise alert frequency and response times.

---

## AWS Deployment Instructions (Summary)

See the full guide: [`infrastructure/deployment-guide.md`](infrastructure/deployment-guide.md)

**Quick steps:**
1. Create DynamoDB table `ChatbotAlerts`
2. Create Discord webhook → store URL in Secrets Manager as `physical-chatbot/discord-webhook`
3. Create IAM role `PhysicalChatbotLambdaRole`
4. Create Lambda function `PhysicalChatbotTrigger` (Python 3.12), set env vars
5. Create API Gateway REST API → POST `/alert` → Lambda proxy → Deploy to `prod`
6. Copy Invoke URL into `frontend/script.js`
7. Deploy frontend to S3 static website
8. Open S3 URL in browser → click Send Alert → watch Discord!

---

## Architecture Diagram

```
Browser → API Gateway → Lambda → DynamoDB
                            └──→ Discord (via Webhook)
                                 CloudWatch (Logs)
```

---

## Viva Questions and Answers

**Q1: What is AWS Lambda and why did you use it?**
> AWS Lambda is a serverless compute service. It runs code only when triggered, so you don't need to manage servers. We used it because it's perfect for event-driven tasks like sending a notification — it costs nothing when idle and scales automatically.

**Q2: What is Amazon API Gateway?**
> API Gateway is a managed service that creates HTTP endpoints (URLs) for your backend. It acts as the "front door" to your Lambda function. It handles request routing, throttling, and CORS.

**Q3: What is DynamoDB and what did you store in it?**
> DynamoDB is a fully managed NoSQL database. We store each alert as an item with fields: alertId, message, sender, timestamp, and status (pending/delivered/failed).

**Q4: Why didn't you put the Discord webhook URL in the JavaScript file?**
> JavaScript in a browser is visible to anyone who views the page source. If the webhook URL was there, anyone could steal it and spam our Discord channel. Instead, we store it in AWS Secrets Manager — only our Lambda function can access it.

**Q5: What is CORS and why is it needed?**
> CORS (Cross-Origin Resource Sharing) is a browser security feature that blocks requests to a different domain unless the server explicitly allows it. Our S3 website is on a different domain than API Gateway, so we configured CORS headers on API Gateway and Lambda to allow requests.

**Q6: What are the security measures in this project?**
> 1. Secrets in AWS Secrets Manager, not in code. 2. IAM least-privilege — Lambda can only access its own DynamoDB table and its own secret. 3. API throttling (10 req/sec). 4. Input validation in Lambda. 5. No credentials in the GitHub repository (.gitignore).

**Q7: How much does this project cost on AWS?**
> Approximately $0.40/month (only Secrets Manager has a cost). All other services — Lambda, DynamoDB, API Gateway, S3, CloudWatch — are within the AWS free tier for this usage level.

**Q8: What is the difference between S3 static hosting and a traditional web server?**
> A traditional web server (like Apache or Nginx on an EC2 instance) runs 24/7 and charges you per hour. S3 static hosting just stores files and serves them on request — you pay only for storage (cents per GB) and the small number of requests. There is no server to maintain.

**Q9: What would you improve if you had more time?**
> Add HTTPS using CloudFront, add user authentication with AWS Cognito, and implement real-time history updates using DynamoDB Streams and WebSocket API Gateway.

**Q10: What is a webhook?**
> A webhook is an HTTP callback — a URL that another service calls when something happens. Discord provides webhook URLs for channels. When our Lambda POSTs a JSON message to that URL, Discord displays it in the channel automatically.

---

## Project Information

- **Project Title:** Physical Chatbot Trigger — Cloud Computing Software Version
- **Technology:** AWS Serverless (Lambda, API Gateway, DynamoDB, S3, Secrets Manager)
- **Frontend:** HTML5, CSS3, JavaScript (ES2022)
- **Backend:** Python 3.12
- **Notifications:** Discord Webhook

## .gitignore Reference

See [`.gitignore`](.gitignore) — secrets and credentials are excluded from version control.
