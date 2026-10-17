from io import StringIO
from smtplib import SMTPAuthenticationError, SMTPServerDisconnected
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings


@override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='smtp.gmail.com', EMAIL_HOST_USER='academy@example.com', EMAIL_HOST_PASSWORD='private-test-value')
class EmailSMTPCheckTests(SimpleTestCase):
    def test_checks_connection_without_sending_email(self):
        with patch('accounts.management.commands.check_email_smtp.get_connection') as get_connection:
            output = StringIO()
            call_command('check_email_smtp', stdout=output)
            get_connection.return_value.open.assert_called_once()
            get_connection.return_value.close.assert_called_once()
            get_connection.return_value.send_messages.assert_not_called()
            self.assertIn('muvaffaqiyatli', output.getvalue())

    @override_settings(EMAIL_HOST='academy@example.com')
    def test_email_address_is_rejected_as_smtp_host(self):
        with self.assertRaisesMessage(CommandError, 'EMAIL_HOST=smtp.gmail.com'):
            call_command('check_email_smtp')

    def test_authentication_errors_do_not_disclose_credentials(self):
        with patch('accounts.management.commands.check_email_smtp.get_connection') as get_connection:
            get_connection.return_value.open.side_effect = SMTPAuthenticationError(535, b'private-test-value')
            with self.assertRaises(CommandError) as caught:
                call_command('check_email_smtp')
            self.assertNotIn('private-test-value', str(caught.exception))
            self.assertIn('App password', str(caught.exception))

    def test_disconnect_errors_do_not_disclose_server_contents(self):
        with patch('accounts.management.commands.check_email_smtp.get_connection') as get_connection:
            get_connection.return_value.open.side_effect = SMTPServerDisconnected('private-test-value')
            with self.assertRaises(CommandError) as caught:
                call_command('check_email_smtp')
            self.assertNotIn('private-test-value', str(caught.exception))
            self.assertIn('SMTPServerDisconnected', str(caught.exception))
