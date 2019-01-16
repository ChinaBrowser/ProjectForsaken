#!/usr/bin/python3
import re
import sqlite3
import configparser
import asyncore
import mailparser
import base64
import threading
import time
import sys
import json
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from datetime import datetime
from smtpd import SMTPServer

config = configparser.ConfigParser()
config.read('config.py')

conn = sqlite3.connect(config.get('DATABASE', 'FILE'))
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS mails (timestamp real, sender text, _from text, _to text, body text)')
conn.commit()

class EmlServer(SMTPServer):
    no = 0

    def process_message(self, peer, mailfrom, rcpttos, data):
        parsed = mailparser.parse_from_string(data)
        sender = parsed.from_[0][0]
        _from = parsed.from_[0][1]
        _to = parsed.to[0][1]
        print('New email to %s.' % _to)
        _date = int(time.time())
        body = str(base64.b64encode(parsed.body.encode()), 'utf-8')
        params = (_date, sender, _from, _to, body)
        c.execute('INSERT INTO mails VALUES (?, ?, ?, ?, ?)', params)
        conn.commit()

def cleaner():
    while True:
        time.sleep(int(config.get('CLEANER', 'CLEAN_INTERVAL')))
        c.execute('DELETE FROM mails WHERE timestamp<%d' % int(time.time()-int(config.get('CLEANER', 'KEEP_TIME'))))
        conn.commit()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""

class APIServer(BaseHTTPRequestHandler):

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_GET(self):
        self.conn = sqlite3.connect(config.get('DATABASE', 'FILE'))
        self.c = self.conn.cursor()
        if len(self.path) <= 1:
            self.do_HEAD()
            self.wfile.write(json.dumps({'result': 'false', 'msg': 'Nothing was requested.'}).encode())
            return
        query = urlparse(self.path).query
        query_components = dict(qc.split("=") for qc in query.split("&"))
        if 'email' not in query_components.keys():
            self.do_HEAD()
            self.wfile.write(json.dumps({'result': False, 'msg': 'Unknown parameter(s).'}).encode())
            return
        sqlQuery = 'SELECT * FROM mails' if query_components['email'] == 'all' else 'SELECT * FROM mails WHERE _to=\'%s\'' % query_components['email']
        mails = []
        for row in self.c.execute(sqlQuery):
            mails.append({
                       'timestamp': row[0],
                       'from' : row[1],
                       'from_address' : row[2],
                       'to' : row[3],
                       'body' : row[4]
                  })
        counts = len(mails)
        ret = {
            'result': True,
            'counts': counts,
            'mails' : mails,
            'msg' : 'Emails for %s' % query_components['email']
        }
        self.do_HEAD()
        self.wfile.write(json.dumps(ret).encode())

class hs:

    def __init__(self):
        th = threading.Thread(target=self.run, daemon=True).start()

    def kill(self):
        self.httpd.shutdown()

    def run(self):
        self.httpd = ThreadedHTTPServer(('', int(config.get('API', 'PORT'))), APIServer)
        self.httpd.timeout = 2
        self.httpd.serve_forever()
        sys.exit()

def run():
    threading.Thread(target=cleaner, daemon=True).start()
    hsd = hs()
    foo = EmlServer(('0.0.0.0', 25), None)
    try:
        asyncore.loop()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
	run()
