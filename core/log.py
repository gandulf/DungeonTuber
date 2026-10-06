import collections
import logging
import os
from pathlib import Path

from core.utils import get_user_data_dir

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
    data_dir = os.environ.get("DT_DATA_DIR")
    log_dir = (Path(data_dir) if data_dir else get_user_data_dir()) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_dir.joinpath('debug.log'), encoding="utf-8")
    console_handler = logging.StreamHandler()

    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("DEBUG") else logging.WARNING,
        style='{',
        format='[{levelname}] {message}',
        force=True,
        handlers=[file_handler,console_handler]
    )
    logging.setLogRecordFactory(StrFormatLogRecord)
