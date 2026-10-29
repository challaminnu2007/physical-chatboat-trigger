# Physical Chatbot Trigger — Complete AWS Deployment Guide

> **Audience:** Complete beginner to AWS cloud deployment.  
> **Estimated time:** 60–90 minutes for first deployment.  
> **AWS Free Tier:** All services used are free-tier eligible, but read the cost notes in each step.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [AWS Account & Region](#2-aws-account--region)
3. [Create the DynamoDB Table](#3-create-the-dynamodb-table)
4. [Create the Discord Webhook](#4-create-the-discord-webhook)
5. [Store the Webhook Securely](#5-store-the-webhook-url-in-aws-secrets-manager)
6. [Create the Lambda IAM Role](#6-create-the-lambda-iam-role)
7. [Create the Lambda Function](#7-create-the-lambda-function)
8. [Create the API Gateway](#8-create-the-api-gateway)
9. [Deploy the Frontend to S3](#9-deploy-the-frontend-to-amazon-s3)
10. [Connect Frontend to API](#10-connect-the-frontend-to-your-api)
11. [End-to-End Testing](#11-end-to-end-testing)
12. [AWS Cost Overview](#12-aws-cost-overview--free-tier)
13. [Cleanup After Demo](#13-cleanup-after-demo)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Prerequisites

Install the following on your computer before starting:

| Tool | Why needed | Install |
|------|-----------|---------|
| AWS CLI v2 | Deploy and manage AWS from terminal | https://aws.amazon.com/cli/ |
| Python 3.11+ | Run local tests | https://python.org |
| VS Code | Edit project files | https://code.visualstudio.com |
| Git | Version control | https://git-scm.com |

**Verify AWS CLI is installed:**
```powershell
aws --version
# Should print: aws-cli/2.x.x ...
```

**Configure AWS CLI with your credentials:**
```powershell
aws configure
# AWS Access Key ID:     <paste your key>
# AWS Secret Access Key: <paste your secret>
# Default region name:   us-east-1
# Default output format: json
```

> **Where to get AWS credentials:**  
> AWS Console → top-right menu → Security Credentials → Access Keys → Create access key.  
> Store the downloaded CSV file safely — you cannot view the secret key again.

---

## 2. AWS Account & Region

### 2.1 Create / Verify AWS Account
- Go to https://aws.amazon.com and sign in or create a free account.
- A credit card is required for verification but **you will not be charged** if you stay within free-tier limits.

### 2.2 Choose a Region
Use **US East (N. Virginia) — us-east-1** for this project.  
All steps in this guide use `us-east-1`. If you change region, update every command that includes a region.

### 2.3 Enable MFA (Recommended)
AWS Console → IAM → Users → your user → Security credentials → Assign MFA device.

---

## 3. Create the DynamoDB Table

### Using AWS Console (Recommended for Beginners)

1. Open https://console.aws.amazon.com/dynamodb
2. Click **Create table**
3. Fill in:
   - **Table name:** `ChatbotAlerts`
   - **Partition key:** `alertId` (String)
   - **Sort key:** leave blank
4. Leave **Table settings** as **Default settings** (uses on-demand billing — free tier: 25 GB storage, 200M read/write requests per month)
5. Click **Create table**
6. Wait until the status shows **Active**

### Using AWS CLI
```powershell
aws dynamodb create-table `
  --table-name ChatbotAlerts `
  --attribute-definitions AttributeName=alertId,AttributeType=S `
  --key-schema AttributeName=alertId,KeyType=HASH `
  --billing-mode PAY_PER_REQUEST `
  --region us-east-1
```

**Verify:**
```powershell
aws dynamodb describe-table --table-name ChatbotAlerts --region us-east-1 --query "Table.TableStatus"
# Should print: "ACTIVE"
```

> **Cost:** DynamoDB free tier gives 25 GB storage and 25 WCU/RCU per month. This project stores tiny records — cost is effectively $0.

---

## 4. Create the Discord Webhook

1. Open Discord and go to a channel where you want alerts to appear (create a new one like `#alerts`)
2. Click the **⚙️ gear icon** next to the channel name → **Integrations** → **Webhooks**
3. Click **New Webhook**
4. Give it a name like `Chatbot Trigger`
5. Click **Copy Webhook URL** — it looks like:  
   `https://discord.com/api/webhooks/1234567890/abcdef...`
6. **Save this URL somewhere temporarily** — you will store it in Secrets Manager in the next step

> ⚠️ **Never paste this URL into your code or commit it to GitHub.**

---

## 5. Store the Webhook URL in AWS Secrets Manager

### Using AWS Console

1. Open https://console.aws.amazon.com/secretsmanager
2. Click **Store a new secret**
3. Select **Other type of secret**
4. Under **Key/value pairs**, add:
   - Key: `webhook_url`
   - Value: (paste your Discord webhook URL)
5. Click **Next**
6. Secret name: `physical-chatbot/discord-webhook`
7. Click **Next** → **Next** → **Store**

### Using AWS CLI
```powershell
aws secretsmanager create-secret `
  --name "physical-chatbot/discord-webhook" `
  --description "Discord webhook for Physical Chatbot Trigger" `
  --secret-string '{"webhook_url":"https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"}' `
  --region us-east-1
```

Note the **Secret ARN** — you will need it for the IAM policy.

> **Cost:** Secrets Manager costs $0.40/secret/month. One secret ≈ $0.40/month.  
> Free-tier note: Secrets Manager has NO free tier. Budget ~$0.40/month or use the DISCORD_WEBHOOK_URL environment variable during development to avoid this cost.

---

## 6. Create the Lambda IAM Role

### Using AWS Console

1. Open https://console.aws.amazon.com/iam → **Roles** → **Create role**
2. Select **AWS service** → **Lambda** → **Next**
3. Search and attach these policies:
   - `AWSLambdaBasicExecutionRole` (pre-built, allows CloudWatch Logs)
4. Click **Next** → Role name: `PhysicalChatbotLambdaRole` → **Create role**

**Add DynamoDB and Secrets Manager permissions:**

5. Click on the new role → **Add permissions** → **Create inline policy**
6. Switch to **JSON** tab and paste:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DynamoDBWriteAlerts",
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:GetItem"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:YOUR_ACCOUNT_ID:table/ChatbotAlerts"
    },
    {
      "Sid": "ReadDiscordSecret",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT_ID:secret:physical-chatbot/discord-webhook*"
    }
  ]
}
```

> Replace `YOUR_ACCOUNT_ID` with your 12-digit AWS account ID (find it at top-right of console).

7. Click **Next** → Policy name: `PhysicalChatbotInlinePolicy` → **Create policy**

---

## 7. Create the Lambda Function

### 7.1 Zip the Backend Code

In your terminal (from the project root):
```powershell
# Windows PowerShell
cd "c:\code\demo cloud\backend"
Compress-Archive -Path lambda_function.py -DestinationPath lambda_deployment.zip -Force
```

### 7.2 Create the Function

**Using AWS Console:**

1. Open https://console.aws.amazon.com/lambda → **Create function**
2. Select **Author from scratch**
3. Fill in:
   - **Function name:** `PhysicalChatbotTrigger`
   - **Runtime:** `Python 3.12`
   - **Architecture:** `x86_64`
4. Under **Permissions** → **Use an existing role** → select `PhysicalChatbotLambdaRole`
5. Click **Create function**

**Upload the code:**
6. In the function page → **Code** tab → **Upload from** → **.zip file**
7. Upload `backend/lambda_deployment.zip`
8. Make sure **Handler** is set to `lambda_function.lambda_handler`

**Using AWS CLI (alternative):**
```powershell
aws lambda create-function `
  --function-name PhysicalChatbotTrigger `
  --runtime python3.12 `
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/PhysicalChatbotLambdaRole `
  --handler lambda_function.lambda_handler `
  --zip-file fileb://backend/lambda_deployment.zip `
  --region us-east-1
```

### 7.3 Set Environment Variables

In the Lambda console → **Configuration** tab → **Environment variables** → **Edit**:

| Key | Value |
|-----|-------|
| `DYNAMODB_TABLE_NAME` | `ChatbotAlerts` |
| `DISCORD_SECRET_NAME` | `physical-chatbot/discord-webhook` |
| `ALLOWED_ORIGIN` | `*` (change to your S3 URL after deployment) |

Click **Save**.

### 7.4 Configure Timeout and Memory

**Configuration** → **General configuration** → **Edit**:
- **Memory:** `128 MB` (minimum — sufficient for this function)
- **Timeout:** `15 seconds` (Discord can be slow occasionally)

### 7.5 Test the Lambda Function

In the Lambda console → **Test** tab → **Create new event**:

```json
{
  "httpMethod": "POST",
  "body": "{\"message\": \"Test alert from Lambda console!\", \"sender\": \"Lambda Test\"}",
  "headers": {}
}
```

Click **Test**. Expected result:
```json
{
  "statusCode": 200,
  "body": "{\"alertId\": \"...\", \"discordStatus\": \"sent\", ...}"
}
```

Check your Discord channel — you should see the alert message appear! 🎉

> **Cost:** Lambda free tier: 1 million requests/month + 400,000 GB-seconds compute. This project will cost $0 in Lambda.

---

## 8. Create the API Gateway

### 8.1 Create the REST API

1. Open https://console.aws.amazon.com/apigateway
2. Click **Create API** → **REST API** → **Build**
3. Select **New API**
4. **API name:** `physical-chatbot-api`
5. **Endpoint type:** `Regional`
6. Click **Create API**

### 8.2 Create the Resource and Method

1. In the API, click **Actions** → **Create Resource**
2. **Resource Name:** `alert`
3. **Resource Path:** `/alert`
4. ✅ Check **Enable API Gateway CORS**
5. Click **Create Resource**

6. Select the `/alert` resource → **Actions** → **Create Method** → **POST** → ✔️
7. Setup:
   - **Integration type:** `Lambda Function`
   - **Use Lambda Proxy integration:** ✅ checked
   - **Lambda Region:** `us-east-1`
   - **Lambda Function:** `PhysicalChatbotTrigger`
8. Click **Save** → confirm the permission dialog

### 8.3 Enable CORS

1. Select `/alert` → **Actions** → **Enable CORS**
2. **Access-Control-Allow-Origin:** `*` (change to your S3 URL after frontend deployment)
3. Click **Enable CORS and replace existing CORS headers** → **Yes, replace existing values**

### 8.4 Add Request Throttling (Security)

1. Click **Usage Plans** in the left menu → **Create**
2. **Name:** `ChatbotThrottle`
3. **Throttling:** Rate `10` req/sec, Burst `20`
4. **Quota:** `1000` requests per day
5. Create and link your API stage to this plan

### 8.5 Deploy the API

1. **Actions** → **Deploy API**
2. **Deployment stage:** **[New Stage]**
3. **Stage name:** `prod`
4. Click **Deploy**

5. **Copy the Invoke URL** — it looks like:
   ```
   https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod
   ```

**Your API endpoint is:**
```
https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod/alert
```

> **Test with curl:**
> ```powershell
> $headers = @{ 'Content-Type' = 'application/json' }
> $body = '{"message":"Hello from curl!","sender":"Test"}'
> Invoke-RestMethod -Uri "https://YOUR_ID.execute-api.us-east-1.amazonaws.com/prod/alert" `
>   -Method POST -Headers $headers -Body $body
> ```

> **Cost:** API Gateway free tier: 1 million API calls/month for 12 months. After that, $3.50 per million calls. For a college demo, cost is $0.

---

## 9. Deploy the Frontend to Amazon S3

### 9.1 Create an S3 Bucket

```powershell
# Replace YOUR_UNIQUE_NAME with something unique (no capitals, no spaces)
aws s3 mb s3://physical-chatbot-trigger-YOUR_UNIQUE_NAME --region us-east-1
```

### 9.2 Enable Static Website Hosting

```powershell
aws s3 website s3://physical-chatbot-trigger-YOUR_UNIQUE_NAME `
  --index-document index.html `
  --error-document index.html
```

### 9.3 Make the Bucket Publicly Readable

First, disable "Block all public access":
```powershell
aws s3api put-public-access-block `
  --bucket physical-chatbot-trigger-YOUR_UNIQUE_NAME `
  --public-access-block-configuration "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"
```

Then apply the bucket policy:
```powershell
$policy = '{"Version":"2012-10-17","Statement":[{"Sid":"PublicReadGetObject","Effect":"Allow","Principal":"*","Action":"s3:GetObject","Resource":"arn:aws:s3:::physical-chatbot-trigger-YOUR_UNIQUE_NAME/*"}]}'
aws s3api put-bucket-policy `
  --bucket physical-chatbot-trigger-YOUR_UNIQUE_NAME `
  --policy $policy
```

### 9.4 Upload Frontend Files

```powershell
cd "c:\code\demo cloud"
aws s3 sync frontend/ s3://physical-chatbot-trigger-YOUR_UNIQUE_NAME/ `
  --exclude "*.md" `
  --region us-east-1
```

Your website URL will be:
```
http://physical-chatbot-trigger-YOUR_UNIQUE_NAME.s3-website-us-east-1.amazonaws.com
```

> **Cost:** S3 free tier: 5 GB storage, 20,000 GET requests, 2,000 PUT requests per month for 12 months. This project uses < 1 MB. Cost = $0.

---

## 10. Connect the Frontend to Your API

### 10.1 Update script.js with Your Real API Endpoint

Open `frontend/script.js` and change line 17:

```javascript
// BEFORE (placeholder):
const API_ENDPOINT = 'YOUR_API_GATEWAY_INVOKE_URL_HERE';

// AFTER (your real URL):
const API_ENDPOINT = 'https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod/alert';
```

### 10.2 Update CORS for Your S3 URL

1. In Lambda console → **Configuration** → **Environment variables**
2. Change `ALLOWED_ORIGIN` to:
   ```
   http://physical-chatbot-trigger-YOUR_UNIQUE_NAME.s3-website-us-east-1.amazonaws.com
   ```

3. In API Gateway → `/alert` resource → **Actions** → **Enable CORS**
4. Update **Access-Control-Allow-Origin** to your S3 URL
5. **Deploy API** again (Actions → Deploy API → `prod`)

### 10.3 Re-upload the Updated Frontend

```powershell
cd "c:\code\demo cloud"
aws s3 sync frontend/ s3://physical-chatbot-trigger-YOUR_UNIQUE_NAME/ --region us-east-1
```

---

## 11. End-to-End Testing

### 11.1 Test from the Website

1. Open your S3 website URL in a browser
2. Type a message in the text area (or click a preset button)
3. Click **Send Alert**
4. Check:
   - ✅ Green success toast appears on the website
   - ✅ Alert appears in your Discord channel
   - ✅ Session stats increment

### 11.2 Verify DynamoDB Record

```powershell
aws dynamodb scan --table-name ChatbotAlerts --region us-east-1
```

You should see records with `status: "delivered"`.

### 11.3 View Lambda Logs

```powershell
# Get the latest log stream
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/PhysicalChatbotTrigger

# Stream live logs (tail)
aws logs tail /aws/lambda/PhysicalChatbotTrigger --follow
```

### 11.4 Run Local Unit Tests

```powershell
cd "c:\code\demo cloud"
pip install pytest
pytest tests/ -v
```

All 17 tests should pass with `PASSED`.

---

## 12. AWS Cost Overview & Free Tier

| Service | Free Tier | Estimated Monthly Cost |
|---------|-----------|----------------------|
| Lambda | 1M requests + 400K GB-seconds | **$0** |
| API Gateway | 1M calls for 12 months | **$0** |
| DynamoDB | 25 GB, 25 WCU/RCU | **$0** |
| S3 | 5 GB, 20K GET, 2K PUT for 12 months | **$0** |
| CloudWatch Logs | 5 GB ingestion/month | **$0** |
| Secrets Manager | **No free tier** | **~$0.40/month** |

**Total: ~$0.40/month** (or $0 if you use `DISCORD_WEBHOOK_URL` env var instead of Secrets Manager during development)

> ⚠️ Free tier only applies for **12 months** from account creation (except DynamoDB which is always free).

---

## 13. Cleanup After Demo

To avoid any ongoing charges, delete resources after your presentation:

```powershell
# 1. Delete Lambda function
aws lambda delete-function --function-name PhysicalChatbotTrigger

# 2. Delete API Gateway (find your API ID in console)
aws apigateway delete-rest-api --rest-api-id YOUR_API_ID

# 3. Delete DynamoDB table
aws dynamodb delete-table --table-name ChatbotAlerts

# 4. Delete S3 bucket (must be empty first)
aws s3 rm s3://physical-chatbot-trigger-YOUR_UNIQUE_NAME --recursive
aws s3 rb s3://physical-chatbot-trigger-YOUR_UNIQUE_NAME

# 5. Delete the secret
aws secretsmanager delete-secret `
  --secret-id physical-chatbot/discord-webhook `
  --force-delete-without-recovery

# 6. Delete the IAM role policies and role
aws iam delete-role-policy --role-name PhysicalChatbotLambdaRole --policy-name PhysicalChatbotInlinePolicy
aws iam detach-role-policy --role-name PhysicalChatbotLambdaRole --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name PhysicalChatbotLambdaRole
```

---

## 14. Troubleshooting

### "CORS error" in browser console
- Make sure you clicked **Deploy API** after enabling CORS
- Check that `ALLOWED_ORIGIN` in Lambda env vars matches your frontend URL exactly

### "Internal Server Error" (500) from Lambda
- Open CloudWatch logs: AWS Console → CloudWatch → Log Groups → `/aws/lambda/PhysicalChatbotTrigger`
- Common causes: wrong DynamoDB table name, missing IAM permission

### Discord message not appearing
- Verify the webhook URL in Secrets Manager is correct
- Test webhook manually:
  ```powershell
  $body = '{"content":"Test from Postman"}'
  Invoke-RestMethod -Uri "YOUR_WEBHOOK_URL" -Method POST -ContentType "application/json" -Body $body
  ```

### "AccessDeniedException" in Lambda logs
- The IAM role is missing a permission — add it in the inline policy

### API Endpoint shows 403 Forbidden
- Redeploy the API: API Gateway → Actions → Deploy API

### S3 website shows "403 Access Denied"
- Verify the bucket policy was applied and public access block was disabled

### Local tests fail with "ModuleNotFoundError: No module named 'boto3'"
- The test file stubs boto3, so this should not happen. If it does:
  ```powershell
  pip install boto3 pytest
  pytest tests/ -v
  ```
