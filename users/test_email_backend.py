"""
Tests for the Resend email backend.

The HTTP client is stubbed, so these tests never make a network
call. They cover the payload the backend builds and the way it
handles a missing key, a failed request and an unexpected
response shape.
"""

from unittest import mock

import resend
import resend.exceptions
from django.core.mail import EmailMultiAlternatives, send_mail
from django.test import SimpleTestCase, override_settings

from users.email_backend import ResendEmailBackend


@override_settings(
    RESEND_API_KEY='re_test_key',
    DEFAULT_FROM_EMAIL='StudyBuddy <no-reply@example.com>',
)
class ResendEmailBackendTests(SimpleTestCase):

    def build_backend(self, **kwargs):

        return ResendEmailBackend(**kwargs)

    def logged(self, logger):
        """Everything the backend wrote to the error log."""
        return ' '.join(
            str(call)
            for call in logger.error.call_args_list
        )

    def test_no_messages_returns_zero_without_calling_the_api(self):
        with mock.patch('resend.Emails.send') as send:

            result = self.build_backend().send_messages([])

        self.assertEqual(result, 0)
        send.assert_not_called()

    def test_missing_api_key_raises_when_not_silent(self):
        with override_settings(RESEND_API_KEY=''):

            with self.assertRaises(RuntimeError):

                self.build_backend().send_messages([self.message()])

    def test_missing_api_key_is_logged_when_silent(self):
        with override_settings(RESEND_API_KEY=''):

            with mock.patch(
                'users.email_backend.logger'
            ) as logger:

                result = self.build_backend(
                    fail_silently=True
                ).send_messages([self.message()])

        self.assertEqual(result, 0)
        logger.error.assert_called_once()

    def test_plain_message_payload(self):
        with mock.patch('resend.Emails.send') as send:

            send.return_value = {
                'id': 'msg_123'
            }

            result = self.build_backend().send_messages([
                self.message()
            ])

        self.assertEqual(result, 1)

        payload = send.call_args[0][0]

        self.assertEqual(
            payload['from'],
            'StudyBuddy <no-reply@example.com>'
        )

        self.assertEqual(
            payload['to'],
            ['student@example.com']
        )

        self.assertEqual(
            payload['subject'],
            'Hello'
        )

        self.assertEqual(
            payload['text'],
            'Plain body'
        )

        self.assertNotIn('html', payload)

    def test_message_from_email_wins_over_the_default(self):
        message = self.message()
        message.from_email = 'Override <override@example.com>'

        with mock.patch('resend.Emails.send') as send:

            send.return_value = {'id': 'msg_123'}

            self.build_backend().send_messages([message])

        self.assertEqual(
            send.call_args[0][0]['from'],
            'Override <override@example.com>'
        )

    def test_html_alternative_is_preferred(self):
        message = EmailMultiAlternatives(
            subject='Hello',
            body='Plain body',
            to=['student@example.com'],
        )

        message.attach_alternative(
            '<p>Rich body</p>',
            'text/html'
        )

        with mock.patch('resend.Emails.send') as send:

            send.return_value = {'id': 'msg_123'}

            self.build_backend().send_messages([message])

        payload = send.call_args[0][0]

        self.assertEqual(payload['html'], '<p>Rich body</p>')
        self.assertEqual(payload['text'], 'Plain body')

    def test_counted_messages_in_one_call(self):
        with mock.patch('resend.Emails.send') as send:

            send.return_value = {'id': 'msg_123'}

            result = self.build_backend().send_messages([
                self.message(),
                self.message(),
            ])

        self.assertEqual(result, 2)
        self.assertEqual(send.call_count, 2)

    def test_unexpected_response_raises_when_not_silent(self):
        with mock.patch('resend.Emails.send') as send:

            send.return_value = {
                'unexpected': 'shape'
            }

            with self.assertRaises(RuntimeError):

                self.build_backend().send_messages([
                    self.message()
                ])

    def test_unexpected_response_is_logged_when_silent(self):
        with mock.patch('resend.Emails.send') as send:

            send.return_value = {
                'unexpected': 'shape'
            }

            with mock.patch(
                'users.email_backend.logger'
            ) as logger:

                result = self.build_backend(
                    fail_silently=True
                ).send_messages([self.message()])

        self.assertEqual(result, 0)
        logger.error.assert_called_once()

    def test_api_failure_is_reraised_with_a_useful_error(self):
        # A silent password reset is worse than a visible error, so
        # the original exception must survive. This also guards the
        # `message` variable in the except block, which must still
        # be the email object.

        with mock.patch('resend.Emails.send') as send:

            send.side_effect = OSError('Connection refused')

            with self.assertRaises(OSError) as caught:

                self.build_backend().send_messages([
                    self.message()
                ])

        self.assertIn(
            'Connection refused',
            str(caught.exception)
        )

    def test_api_failure_is_swallowed_when_silent(self):
        with mock.patch('resend.Emails.send') as send:

            send.side_effect = OSError('Connection refused')

            with mock.patch(
                'users.email_backend.logger'
            ) as logger:

                result = self.build_backend(
                    fail_silently=True
                ).send_messages([self.message()])

        self.assertEqual(result, 0)
        logger.error.assert_called_once()

    def test_a_failure_is_logged_with_error_not_exception(self):
        # `logger.exception` would print the raw ResendError message
        # in the traceback, and Resend quotes the recipient inside
        # that message. The reason is logged explicitly instead, and
        # the traceback is kept for DEBUG, which production does not
        # emit.

        with mock.patch('resend.Emails.send') as send:

            send.side_effect = OSError('Connection refused')

            with mock.patch(
                'users.email_backend.logger'
            ) as logger:

                self.build_backend(
                    fail_silently=True
                ).send_messages([self.message()])

        logger.exception.assert_not_called()

    def test_a_resend_rejection_is_logged_with_its_own_reason(self):
        # This is the log line that explains a reset email which was
        # never delivered: the provider's code and message.

        rejection = resend.exceptions.ResendError(
            code=403,
            error_type='validation_error',
            message='Domain is not verified.',
            suggested_action='Verify the domain first.',
        )

        with mock.patch('resend.Emails.send') as send:

            send.side_effect = rejection

            with mock.patch(
                'users.email_backend.logger'
            ) as logger:

                with self.assertRaises(resend.exceptions.ResendError):

                    self.build_backend().send_messages([
                        self.message()
                    ])

        logged = self.logged(logger)

        self.assertIn('403', logged)
        self.assertIn('validation_error', logged)
        self.assertIn('Domain is not verified.', logged)

    def test_the_logged_reason_never_contains_the_recipient(self):
        # Resend replies with the address it rejected, for example
        # "You can only send testing emails to your own email
        # address (student@example.com)". That must not be written to
        # the log.

        rejection = resend.exceptions.ResendError(
            code=403,
            error_type='validation_error',
            message=(
                'You can only send testing emails to your own '
                'email address (student@example.com).'
            ),
            suggested_action='Use a verified domain.',
        )

        with mock.patch('resend.Emails.send') as send:

            send.side_effect = rejection

            with mock.patch(
                'users.email_backend.logger'
            ) as logger:

                with self.assertRaises(resend.exceptions.ResendError):

                    self.build_backend().send_messages([
                        self.message()
                    ])

        logged = self.logged(logger)

        self.assertNotIn('student@example.com', logged)
        self.assertIn('[address redacted]', logged)

    def test_the_logged_reason_never_contains_the_api_key(self):
        rejection = resend.exceptions.ResendError(
            code=401,
            error_type='invalid_api_key',
            message='API key is invalid: re_test_key',
            suggested_action='Check the key.',
        )

        with mock.patch('resend.Emails.send') as send:

            send.side_effect = rejection

            with mock.patch(
                'users.email_backend.logger'
            ) as logger:

                with self.assertRaises(resend.exceptions.ResendError):

                    self.build_backend().send_messages([
                        self.message()
                    ])

        logged = self.logged(logger)

        self.assertNotIn('re_test_key', logged)
        self.assertIn('[api key redacted]', logged)

    def test_an_accepted_message_is_logged_with_its_id(self):
        # The id is the only proof that Resend really took the
        # message, and it identifies nobody.

        with mock.patch('resend.Emails.send') as send:

            send.return_value = {'id': 'msg_123'}

            with mock.patch(
                'users.email_backend.logger'
            ) as logger:

                self.build_backend().send_messages([self.message()])

        message, *arguments = logger.info.call_args[0]

        self.assertIn('Resend accepted', message)
        self.assertIn('msg_123', arguments)
        self.assertIn(1, arguments)

    def test_one_failure_does_not_stop_the_batch(self):
        with mock.patch('resend.Emails.send') as send:

            send.side_effect = [
                OSError('Connection refused'),
                {
                    'id': 'msg_123'
                },
            ]

            with self.assertRaises(OSError):

                self.build_backend().send_messages([
                    self.message(),
                    self.message(),
                ])

    def test_send_mail_through_get_connection(self):
        with mock.patch('resend.Emails.send') as send:

            send.return_value = {
                'id': 'msg_123'
            }

            with override_settings(
                EMAIL_BACKEND=(
                    'users.email_backend.ResendEmailBackend'
                )
            ):

                sent = send_mail(
                    subject='Hello',
                    message='Plain body',
                    from_email=None,
                    recipient_list=[
                        'student@example.com'
                    ],
                    fail_silently=False,
                )

        self.assertEqual(sent, 1)

    def message(self):

        from django.core.mail import EmailMessage

        return EmailMessage(
            subject='Hello',
            body='Plain body',
            to=['student@example.com'],
        )
