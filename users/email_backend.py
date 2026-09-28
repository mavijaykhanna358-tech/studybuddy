import logging
import re

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

import resend


logger = logging.getLogger(__name__)


# Anything that must never reach a log file. Resend echoes the
# recipient back inside its error text, for example
# "You can only send testing emails to your own email address
# (someone@example.com)", so the provider's own message is scrubbed
# before it is written down.

REDACTIONS = (
    # An address, wherever it appears.
    (
        re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'),
        '[address redacted]',
    ),
    # The one-time part of a reset link: /reset/<uidb64>-<token>/
    (
        re.compile(r'/reset/[\w-]+'),
        '/reset/[token redacted]',
    ),
    # A uidb64/token pair, should it appear outside a URL.
    (
        re.compile(r'\b[A-Za-z0-9_\-]{20,}\b'),
        '[token redacted]',
    ),
)


def redact(text, api_key=None):
    """
    Strip credentials, addresses and tokens from text bound for a log.
    """

    if not text:
        return ''

    cleaned = str(text)

    if api_key:
        cleaned = cleaned.replace(
            str(api_key),
            '[api key redacted]'
        )

    for pattern, replacement in REDACTIONS:

        cleaned = pattern.sub(replacement, cleaned)

    return cleaned


def describe(error, api_key=None):
    """
    Summarise a Resend failure in a form that is safe to log.

    Resend's exceptions carry a code, a type, a message and a
    suggested action. The message can quote the recipient, so it is
    redacted. `str(error)` is never used directly, because the
    traceback of a raised ResendError prints the raw message.
    """

    details = []

    for label, value in (
        ('code', getattr(error, 'code', None)),
        ('type', getattr(error, 'error_type', None)),
        ('message', getattr(error, 'message', None)),
        ('action', getattr(error, 'suggested_action', None)),
    ):

        if value:
            details.append(
                f'{label}={redact(value, api_key)}'
            )

    if details:
        return '; '.join(details)

    # A non-Resend failure, for example the library raising before it
    # ever made a request. Redacted on the same rules.

    return redact(error, api_key) or error.__class__.__name__


class ResendEmailBackend(BaseEmailBackend):

    """Email backend built on the Resend HTTP API.

    Two behaviours differ from the SMTP backends and are
    intentional:

    * The sender address is taken from ``DEFAULT_FROM_EMAIL``
      unless a message overrides it.
    * Errors are logged and re-raised so Django's
      ``fail_silently=False`` contract is honoured. A password
      reset that silently fails is worse than a visible error.

    The raised error carries the provider's own code and message,
    which is what makes a rejected send diagnosable from the Render
    log instead of guessing.
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

            message = (
                'RESEND_API_KEY is not set, so no email can be '
                'sent through the Resend backend. Set it on the '
                'Render service.'
            )

            if not self.fail_silently:

                raise RuntimeError(message)

            logger.error(message)

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

                    # The id is the only proof that a message was
                    # really accepted, so it is logged on success.
                    # Neither the id nor the sender identifies a
                    # user.

                    logger.info(
                        'Resend accepted the message '
                        '(id=%s recipients=%d sender=%s).',
                        response['id'],
                        len(message.to),
                        payload['from'],
                    )

                else:

                    detail = (
                        'Resend returned an unexpected response '
                        f'shape, without a message id: '
                        f'{redact(response, api_key)!r}'
                    )

                    logger.error(detail)

                    if not self.fail_silently:

                        raise RuntimeError(detail)

            except RuntimeError:

                # Already reported with its own detail above.

                if not self.fail_silently:

                    raise

            except Exception as error:

                # The reason a reset email went missing lives here,
                # so it is logged in full: the provider's code and
                # message are what a Render log needs. Addresses and
                # tokens are redacted, and `logger.exception` is
                # deliberately not used, because a raised
                # ResendError prints its unredacted message in the
                # traceback.

                logger.error(
                    'Resend rejected the email: %s '
                    '(recipients=%d sender=%s).',
                    describe(error, api_key),
                    len(message.to),
                    payload['from'],
                )

                # The traceback is kept for DEBUG, which the
                # production log level does not emit.

                logger.debug(
                    'Resend failure detail.',
                    exc_info=True,
                )

                if not self.fail_silently:

                    raise

        return sent_count
