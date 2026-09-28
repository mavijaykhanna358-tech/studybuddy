import logging

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

import resend


logger = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):

    """Email backend built on the Resend HTTP API.

    Two behaviours differ from the SMTP backends and are
    intentional:

    * The sender address is taken from ``DEFAULT_FROM_EMAIL``
      unless a message overrides it.
    * Errors are logged and re-raised so Django's
      ``fail_silently=False`` contract is honoured. A password
      reset that silently fails is worse than a visible error.
    """

    def send_messages(self, email_messages):

        if not email_messages:

            return 0

        api_key = getattr(
            settings,
            'RESEND_API_KEY',
            None
        )

        if not api_key:

            if not self.fail_silently:

                raise RuntimeError(
                    'RESEND_API_KEY is not set, so no email '
                    'can be sent through the Resend backend.'
                )

            logger.error(
                'RESEND_API_KEY is missing. '
                'Email delivery was skipped.'
            )

            return 0

        resend.api_key = api_key

        sent_count = 0

        for message in email_messages:

            payload = {
                'from': (
                    message.from_email
                    or settings.DEFAULT_FROM_EMAIL
                ),
                'to': list(message.to),
                'subject': message.subject,
            }

            # Prefer the HTML alternative when one exists, and
            # fall back to the plain text body so every message
            # carries a body. `alternatives` only exists on
            # EmailMultiAlternatives; `send_mail` builds a plain
            # EmailMessage, so it is read defensively.

            alternatives = getattr(
                message,
                'alternatives',
                None
            )

            if alternatives:

                html_body, content_type = alternatives[0]

                if content_type == 'text/html':

                    payload['html'] = html_body
                    payload['text'] = message.body

                else:

                    payload['text'] = html_body

            else:

                payload['text'] = message.body

            try:

                response = resend.Emails.send(
                    payload
                )

                # Resend returns a dict with an ``id`` on
                # success and raises on failure.

                if isinstance(response, dict) and response.get(
                    'id'
                ):

                    sent_count += 1

                else:

                    detail = (
                        'Resend returned an unexpected '
                        f'response: {response!r}'
                    )

                    if self.fail_silently:

                        logger.error(detail)

                    else:

                        raise RuntimeError(detail)

            except Exception:

                logger.exception(
                    'Failed to send email to %s',
                    ', '.join(message.to)
                )

                if not self.fail_silently:

                    raise

        return sent_count
