"""
## TODO

* Support non-inline links.
* Support links over multiple lines
   * Probably need a MAX_LINES_TO_SEARCH to stop us looking at lots of lines
"""
import pathlib
import re
import urllib

import pynvim

# Match text and URL from an inline Markdown link
# Taken from https://stackoverflow.com/a/40178293
# Modified to allow spaces in the URL
LINK_RE = re.compile(r'\[([^]]*)\]\(([^\)]*)')
NOTES_RE = re.compile(r'\[\[(.*)\]\]')
# A Markdown URL can contain an optional title, separated from the URL by at
# least one space and surrounded by quotes
URL_RE = re.compile(r'([^\'^"]+)(\s+[\'"](.*)[\'"])?')


@pynvim.plugin
class FollowMarkdownLinksPlugin:
    def __init__(self, nvim):
        self.nvim = nvim
        self.config = {
            'open_remote': False,
            'debug': True
        }
        # List of (Path, cursor position) tuples
        self.buffer_stack = []

    def markdown_link(self, crow, ccol, line):
        # Index in string containing the start of the link
        # ccol + 1 so that we match when the cursor is *on* the opener
        start_pos = line.rfind('[', 0, ccol + 1)
        if start_pos == -1:
            self.debug('No link opener found before cursor: {}'.format(line[:ccol + 1]))
            return
        end_pos = line.find(')', start_pos)
        if end_pos < ccol:
            self.debug('No link closer found after cursor: {}'.format(line[start_pos:]))
            return

        # endpos + 2 so that we match when the cursor is *on* the closer
        haystack = line[start_pos:end_pos + 1]
        matches = LINK_RE.match(haystack)
        if matches is None:
            self.debug('No matches found: {}'.format(haystack))
            return
        _, href = matches.groups()

        # We have the URL component, now parse out the actual URL and the title
        matches = URL_RE.match(href)
        href, _, _ = matches.groups()
        # This assumes filenames do not have trailing whitespace, and is needed
        # as URL_RE will capture the whitespace between the URL and the title
        # Would be nicer if we could parse this in the URL matching group
        href = href.rstrip()

        # We only handle foillowing local paths
        # Need to escape spaces
        url = urllib.parse.urlparse(href.replace(' ', '%20'))
        if url.scheme:
            if self.config['open_remote']:
                # TODO
                pass
            self.debug('Path is not local: {}'.format(url.geturl()))
            return

        # Get the path to the open buffer
        # https://unix.stackexchange.com/a/320129
        buffer_path = pathlib.Path(self.nvim.eval('expand("%:p")'))
        target_path = (buffer_path.parent / url.path.replace('%20', ' ')).resolve()
        if not target_path.exists():
            extensions = self.nvim.eval('g:follow_markdown_links#extensions') or []
            found_file = False
            for ext in extensions:
                probe = target_path.with_suffix(ext)
                if probe.exists():
                    target_path = probe
                    found_file = True

            # TODO: could print all filenames that we tried
            if not found_file:
                # TODO: print an error/warning?
                self.debug('Path does not exist: {!r} {!r} {!r}'.format(target_path, href, url.path))
                return

        self.buffer_stack.append((buffer_path, (crow, ccol)))

        # TODO: escape quotation marks in path?
        self.debug('Opening path: {}'.format(target_path))
        self.nvim.command('w')
        self.nvim.command('edit {}'.format(target_path))

    def note_link(self, crow, ccol, line, ccol_byte_offset, new_window_flg=0):
        # Index in string containing the start of the link
        # ccol + 1 so that we match when the cursor is *on* the opener
        start_pos = line.rfind('[[', 0, ccol + 1)
        if start_pos == -1:
            self.debug('No link opener found before cursor: {}'.format(line[:ccol + 1]))
            return
        end_pos = line.find(']]', start_pos)
        if end_pos < ccol:
            self.debug('No link closer found after cursor: {}'.format(line[start_pos:]))
            return

        # endpos + 2 so that we match when the cursor is *on* the closer
        haystack = line[start_pos: end_pos + 2]
        matches = NOTES_RE.match(haystack)
        if matches is None:
            self.debug('No matches found: {}'.format(haystack))
            return
        href = matches.groups()[0]

        # We only handle foillowing local paths
        # Need to escape spaces
        url = urllib.parse.urlparse(href.replace(' ', '%20'))
        if url.scheme:
            if self.config['open_remote']:
                # TODO
                pass
            self.debug('Path is not local: {}'.format(url.geturl()))
            return

        # Get the path to the open buffer
        # https://unix.stackexchange.com/a/320129
        buffer_path = pathlib.Path(self.nvim.eval('expand("%:p")'))
        # target_path = (buffer_path.parent / url.path.replace('%20', ' ')).resolve()
        u = url.path.replace('%20', ' ')
        target_path = pathlib.Path(u).expanduser()  # ~/を展開
        if not target_path.exists():
            import subprocess
            import os
            env = dict(os.environ)
            env["VIMRUNTIME"] = "1"
            subprocess.run(["notesnewbyfullpath {0}".format(u)], shell=True, executable='/bin/zsh', env=env)

        if new_window_flg:
            pass
        else:
            self.buffer_stack.append((buffer_path, (crow, ccol_byte_offset)))

        # TODO: escape quotation marks in path?
        self.debug('Opening path: {}'.format(target_path))
        if new_window_flg:
            self.nvim.command('vnew')
        else:
            self.nvim.command('w')
        self.nvim.command('edit {}'.format(target_path))

    @pynvim.function('FollowMarkdownLink', sync=True)
    def follow_markdown_link(self, _):
        # Cursor position
        crow, ccol_byte_offset = self.nvim.current.window.cursor
        self.debug(str(ccol_byte_offset))
        # Current line buffer
        line = self.nvim.current.line
        # real ccol
        sub_b = bytearray(line, encoding="utf-8")[0: ccol_byte_offset].decode()
        ccol = len(sub_b)
        self.debug(str(ccol))
        self.markdown_link(crow, ccol, line)
        self.note_link(crow, ccol, line, ccol_byte_offset, _[0])

    @pynvim.function('PreviousMarkdownBuffer', sync=True)
    def previous_buffer(self, _):
        if not self.buffer_stack:
            self.debug('Empty history stack.')
            return

        target_path, cursor = self.buffer_stack.pop()

        self.debug('Opening path: {}'.format(target_path))
        self.nvim.command('w')
        self.nvim.command('edit {}'.format(target_path))

        # Restore the cursor position
        self.nvim.current.window.cursor = cursor

    def debug(self, msg):
        if self.config['debug']:
            # TODO show this as a list message when logging multiple times? log file?
            self.nvim.out_write(msg + '\n')
