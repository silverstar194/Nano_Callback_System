# MIT License
#
# Copyright (c) 2019 James Coxon
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import socket, time, json, logging, sys
from logging.handlers import RotatingFileHandler
import tornado.gen
import tornado.ioloop
import tornado.iostream
import tornado.tcpserver
import tornado.web
import tornado.websocket
from collections import defaultdict

logger = logging.getLogger(__name__)

file_handler = RotatingFileHandler('callback_server.log', mode='a', maxBytes=5*1024*1024, backupCount=2, encoding=None, delay=0)

handlers = [file_handler]

if not "--silent" in sys.argv[1:]:
    handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(levelname)s] %(asctime)s %(message)s',
    handlers=handlers
)

client_connections = defaultdict(list)
client_hashes = defaultdict(list)
past_blocks = []


class Data_Callback(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    def post(self):
        receive_time = time.time()
        post_data = json.loads(self.request.body.decode('utf-8'))

        logger.info(("{}: {}".format(receive_time, post_data)))

        block_data = json.loads(post_data['block'])
        block_hash = post_data['hash']
        past_blocks.append((block_data, block_hash, receive_time))

        if len(past_blocks) > 500:
            del past_blocks[0]
        logger.info(("{}".format(block_data)))
        if block_hash in client_hashes:
            clients = client_connections[block_hash]
            for client in clients:
                logger.info("{}: {} {}".format(receive_time, client, post_data))
                client.write_message(json.dumps({"block_data":block_data, "time":receive_time}))
                logger.info("Sent data")

class WSHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        logger.info("WebSocket opened: {}".format(self))

    @tornado.gen.coroutine
    def on_message(self, message):
        logger.info('Message from client {}: {}'.format(self, message))
        if message != "Connected":
            try:
                ws_data = json.loads(message)
                if 'hash' not in ws_data:
                    logger.error('Incorrect data from client: {}'.format(ws_data))
                    raise Exception('Incorrect data from client: {}'.format(ws_data))

                logger.info(ws_data['hash'])

                client_connections[ws_data['hash']].append(self)
                client_hashes[self].append(ws_data['hash'])

                ##handle past blocks for race condition
                for block in past_blocks:
                    logger.info("{}".format(block[1]))
                    if block[1] == ws_data['hash']:
                        for client in client_connections[ws_data['hash']]:
                            logger.info("{} {}: {}".format(block[0], block[1], block[2]))
                            client.write_message(json.dumps({"hash":block[1], "time":block[2]}))
                            logger.info("Sent data")

            except Exception as e:
                logger.error("Error {}".format(e))

    def on_close(self):
        logger.info('Client disconnected - {}'.format(self))
        accounts = client_connections[self]
        for account in accounts:
            client_connections[account].remove(self)
            if len(client_connections[account]) == 0:
                del client_connections[account]
        del client_connections[self]

application = tornado.web.Application([
    (r"/callback/", Data_Callback),
    (r"/call", WSHandler),
])


def main():

    # websocket server
    myIP = socket.gethostbyname(socket.gethostname())
    logger.info('Websocket Server Started at %s' % myIP)

    # callback server
    application.listen(7090)

    # infinite loop
    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    main()
