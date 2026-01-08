import collections
import logging

class StrFormatLogRecord(logging.LogRecord):
    """
    Drop-in replacement for ``LogRecord`` that supports ``str.format``.
    """
    def getMessage(self):
        msg = str(self.msg)
        if self.args:
            try:
                msg = msg % ()
            except TypeError:
                # Either or the two is expected indicating there's
                # a placeholder to interpolate:
                #
                # - not all arguments converted during string formatting
                # - format requires a mapping" expected
                #
                # If would've been easier if Python printf-style behaved
                # consistently for "'' % (1,)" and "'' % {'foo': 1}". But
                # it raises TypeError only for the former case.
                msg = msg % self.args
            else:
                # There's special case of first mapping argument. See duner init of logging.LogRecord.
                if isinstance(self.args, collections.abc.Mapping):
                    msg = msg.format(**self.args)
                else:
                    msg = msg.format(*self.args)

        return msg


def setup_logging():
    logging.basicConfig(
        level=logging.WARNING,
        style='{',
        format='[{levelname}] {message}'
    )
    logging.setLogRecordFactory(StrFormatLogRecord)
