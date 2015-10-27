import sys
import signal
import locale
import logging

import praw
import praw.errors
import tornado
from requests import exceptions

from . import config
from .exceptions import RTVError
from .curses_helpers import curses_session, LoadScreen, prompt_yesno
from .submission import SubmissionPage
from .subreddit import SubredditPage
from .docs import AGENT
from .oauth import OAuthTool
from .__version__ import __version__

__all__ = []
_logger = logging.getLogger(__name__)

# Pycharm debugging note:
# You can use pycharm to debug a curses application by launching rtv in a
# console window (python -m rtv) and using pycharm to attach to the remote
# process. On Ubuntu, you may need to allow ptrace permissions by setting
# ptrace_scope to 0 in /etc/sysctl.d/10-ptrace.conf.
# http://blog.mellenthin.de/archives/2010/10/18/gdb-attach-fails


def main():
    "Main entry point"

    # Handle SIGINT to ask for confirmation
    def sigint_handler(signal, frame):
        if prompt_yesno(stdscr, "Do you really want to quit? (y/n): "):
            sys.exit()
    signal.signal(signal.SIGINT, sigint_handler)

    # Squelch SSL warnings
    logging.captureWarnings(True)
    locale.setlocale(locale.LC_ALL, '')

    # Set the terminal title
    # TODO: Need to clear the title when the program exits
    title = 'rtv {0}'.format(__version__)
    sys.stdout.write("\x1b]2;{0}\x07".format(title))

    # Fill in empty arguments with config file values. Parameters explicitly
    # typed on the command line will take priority over config file params.
    parser = config.build_parser()
    args = parser.parse_args()

    local_config = config.load_config()
    for key, val in local_config.items():
        if getattr(args, key, None) is None:
            setattr(args, key, val)

    if args.ascii:
        config.unicode = False
    if not args.persistent:
        config.persistent = False
    if args.clear_auth:
        config.clear_refresh_token()

    if args.log:
        logging.basicConfig(level=logging.DEBUG, filename=args.log)
    else:
        logging.root.addHandler(logging.NullHandler())

    with curses_session() as stdscr:
        try:
            print('Connecting...')
            reddit = praw.Reddit(user_agent=AGENT.format(version=__version__))
            reddit.config.decode_html_entities = False
            oauth = OAuthTool(reddit, stdscr, LoadScreen(stdscr))
            if oauth.refresh_token:
                oauth.authorize()

            if args.link:
                page = SubmissionPage(stdscr, reddit, oauth, url=args.link)
                page.loop()
            subreddit = args.subreddit or 'front'

            if reddit.is_oauth_session():
                with LoadScreen(stdscr)(message="Loading subreddits"):
                    subscriptions = reddit.get_my_subreddits(limit=None)
                    subscription_names = sorted([str(subreddit) for subreddit in \
                            list(subscriptions)])
            else:
                subscription_names = []

            page = SubredditPage(stdscr, reddit, oauth, subreddit,\
                    subscription_names=subscription_names)
            page.loop()
        except (exceptions.RequestException, praw.errors.PRAWException,
                RTVError) as e:
            _logger.exception(e)
            print('{}: {}'.format(type(e).__name__, e))
        except KeyboardInterrupt:
            # Not sure why we need a duplicate when we already handled the SIGINT
            # but oh well
            if prompt_yesno(stdscr, "Do you really want to quit? (y/n): "):
                sys.exit()
        finally:
            # Ensure sockets are closed to prevent a ResourceWarning
            reddit.handler.http.close()
            # Explicitly close file descriptors opened by Tornado's IOLoop
            tornado.ioloop.IOLoop.current().close(all_fds=True)

sys.exit(main())
