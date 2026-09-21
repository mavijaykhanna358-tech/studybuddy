import os
import resend

from django.core.mail.backends.base import BaseEmailBackend


class ResendEmailBackend(BaseEmailBackend):

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        resend.api_key = os.getenv("RESEND_API_KEY")

        sent = 0

        for message in email_messages:
            try:
                resend.Emails.send({
                    "from": "noreply@studybuddyapp.in.net",
                    "to": message.to,
                    "subject": message.subject,
                    "text": message.body,
                })

                sent += 1

            except Exception as e:
                print("Resend email error:", e)

        return sent
