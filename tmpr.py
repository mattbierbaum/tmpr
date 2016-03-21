import os
import json
import base64
import string
import random

import tornado
import tornado.web
import tornado.ioloop
import tornado.options

# set the root directory for data, by default we should only be working in the
# current directory where this python file lives
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'files')
CHARS = string.ascii_lowercase + ''.join(map(str, xrange(10)))

tornado.options.options.define("port", default=8888)
tornado.options.options.define("root", default=ROOT, help='directory for files')
tornado.options.options.define("addr", default="127.0.0.1", help="port to listen on")

FAVICON =  "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAMAAABEpIrGAAAABGdBTUEAALGPC/xhBQAAAGBQTFRFooKnN8jxY5PVM7vvM7zwY5LUN8fxo4KnhInAuX2Py3172oZtSZ/k5ZJjOa7s6pxbP9LyTNjy66VYVtryo4Vmqoxo57Fit5djvp1lw6Jnzaps17Fu3bNt47Rp6a1csZJmx8KbeAAAAEJJREFUOMtjEBGVl5cXl5CUkpaRlRWTkxPi5+Xm4mTgYOXhY2YTEBRmGNEK2EcVEKuAiRgFjFRXIEOqApZRBSQoAAAJHkuVEmG+EwAAAABJRU5ErkJggg=="

INDEX_CONTENT = \
string.Template("""
<link id="favicon" rel="shortcut icon" type="image/png"
 href="data:image/png;base64,$favicon">

<html><head><title>tmpr : file share</title></head>
<center><pre style='font-size:48px;'>TMPR : FILE SHARING</pre></center>
<pre style='width:640px;margin:auto;'>
Usage : 
    GET
        tmper/              -- this information
        tmper/[CODE]?ARGS   -- get a file given by CODE

    POST
        tmper/              -- upload a file and receive a name
        tmper/[CODE]?ARGS   -- upload file to a particular name

    ARGS :
        key -- set a password for a particular file
        n   -- number of times a file can be downloaded


# function for .bashrc to simplify upload
function tmpr() {
    curl -X POST -F file=@"$$1" &lt;url&gt;
}
</pre>
<br/><center>
<form enctype="multipart/form-data" action='/' method='post'>
<input type='submit' value='Upload'><input type='file' id='filearg' name='filearg'>
</form></center>
<!--<script type='text/javascript>
document.getElementById("filearg").onchange = function() {
    document.getElementById("form").submit();
};
</script>-->
</html>
""").substitute(favicon=FAVICON)

#=============================================================================
# The actual web application now
#=============================================================================
class Application(tornado.web.Application):
    def __init__(self):
        handlers = [(r"/([a-z0-9]{2})?", MainHandler)]
        super(Application, self).__init__(handlers, gzip=True)

class MainHandler(tornado.web.RequestHandler):
    def generate_name(self):
        return ''.join([random.choice(CHARS) for i in xrange(2)])

    def unique_name(self):
        tries, out = 0, self.generate_name()
        while self.exists(out):
            if tries < len(CHARS)**2:
                raise Exception

            out = self.generate_name()
            tries += 1
        return out

    def path(self, n):
        return os.path.join(ROOT, n)

    def pathj(self, n):
        return os.path.join(ROOT, n+'.json')

    def save_file(self, name, content, meta):
        with open(self.path(name), 'w') as f:
            f.write(content)

        with open(self.pathj(name), 'w') as f:
            f.write(json.dumps(meta))

    def open_file(self, name):
        data = open(self.path(name)).read()
        meta = json.loads(open(self.pathj(name)).read())
        return data, meta

    def delete_file(self, name):
        os.remove(self.path(name))
        os.remove(self.pathj(name))

    def exists(self, name):
        return os.path.isfile(self.path(name))

    def error(self, text):
        self.clear()
        self.set_status(404)
        self.write(text)
        self.finish()

    def serve_file(self, data, meta):
        self.set_header('Content-Type', meta['content_type'])
        self.set_header('Content-Disposition', 'attachment; filename=' + meta['filename'])
        self.write(data)
        self.finish()

    def write_formatted(self, data, meta):
        typ = meta['content_type']

        if 'image' in typ:
            self.write("<img src='data:%s;base64,%s'/>" % (typ, base64.b64encode(data)))
        elif 'text' in typ:
            self.write('<pre>%s</pre>' % data)
        else:
            self.serve_file(data, meta)

    def get(self, args):
        agent = self.request.headers['User-Agent']

        if not args:
            self.write(INDEX_CONTENT)
            self.finish()
        else:
            if not self.exists(args):
                self.error('not found')
                return

            data, meta = self.open_file(args)
            meta['n'] -= 1

            # either delete the file or update the view count in the meta data
            if meta['n'] == 0:
                self.delete_file(args)
            else:
                self.save_file(args, data, meta)

            # if we are on command line, just return data, otherwise display it pretty
            if 'curl' in agent or 'Wget' in agent:
                self.write(data)
            else:
                self.write_formatted(data, meta)
            self.finish()

    def post(self, args):
        meta = {}
        meta['key'] = self.request.arguments.get('key', [None])[0]
        usern = int(self.request.arguments.get('n', [1])[0])
        usern = max(min(usern, 10), 0)
        meta['n'] = usern

        # change to error occured since file already exists
        if args and self.exists(args):
            self.error('exists')
            return

        if len(self.request.files) == 1:
            # we have files attached, save each of them to new file names
            name = args or self.unique_name()
            fobj = self.request.files.values()[0][0]

            # separate the actual contents from the meta data
            body = fobj.pop('body')
            meta.update(fobj)

            # write the file and return the accepted name
            self.save_file(name, body, meta)
            self.write(name)
            self.finish()
            return

        self.error('improper payload')

if __name__ == "__main__":
    #web.ErrorHandler = webutil.ErrorHandler
    tornado.options.parse_command_line()

    ROOT = tornado.options.options.root
    if not os.path.exists(ROOT):
        os.mkdir(ROOT)

    app = Application()
    app.listen(tornado.options.options.port, tornado.options.options.addr)
    tornado.ioloop.IOLoop.instance().start()

