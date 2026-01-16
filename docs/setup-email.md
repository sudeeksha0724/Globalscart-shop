# Email/OTP Setup for GlobalCart-360

## Option 1: SendGrid (recommended)

1. **Sign up** at [https://signup.sendgrid.com/](https://signup.sendgrid.com/)
2. **Verify your sender**  
   - Go to **Settings > Sender Authentication**  
   - Verify a single sender or complete domain authentication.  
   - The email you use in `SENDGRID_FROM_EMAIL` must be verified here.
3. **Create an API Key**  
   - **Settings > API Keys > Create API Key**  
   - Choose **Restricted Access**  
   - Enable **Mail Send** permission only  
   - Copy the key (starts with `SG.`)
4. **Set environment variables** in your `.env`:
   ```env
   SENDGRID_API_KEY=SG.xxxxx...
   SENDGRID_FROM_EMAIL=noreply@yourdomain.com
   ```
5. **Restart** the backend: `make dev`

## Option 2: SMTP (Gmail App Password)

1. **Enable 2FA** on your Gmail account
2. **Create an App Password**  
   - Go to [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)  
   - Select app: Mail, device: Other (Custom name)  
   - Copy the 16-character password
3. **Set environment variables** in your `.env`:
   ```env
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USE_TLS=1
   SMTP_USER=you@gmail.com
   SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx   # 16-char App Password
   SMTP_FROM_EMAIL=you@gmail.com
   ```
4. **Restart** the backend: `make dev`

## Verify

- Try signing up on the Shop (`/shop/login.html`) with a new email.
- Check the email inbox for the OTP.
- If email isn’t configured, the API will still return `demo_otp` in the response (when `DEMO_SHOW_OTP=1`).

## Production

- Set `DEMO_SHOW_OTP=0` to avoid exposing OTPs in API responses.
- Use a dedicated transactional email service (SendGrid or your own SMTP).
