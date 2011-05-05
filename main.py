#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# ----------------------------------
# Simple Site Manager For Google App Engine (ssm4gae)

import datetime,mimetypes,os,urllib
from google.appengine.api import users
from google.appengine.dist import use_library
use_library('django','0.96')
from google.appengine.ext import blobstore,db,webapp
from google.appengine.ext.webapp import blobstore_handlers,template,util

# 予約済みパス
LIST_PATH  ='/admin_listcontent'
EDIT_PATH  ='/admin_editcontent'
UPLOAD_PATH='/admin_uploadfile'

class Content(db.Model):
    # key_name = 'e'+path
    name = db.StringProperty()
    path = db.StringProperty(required=True)
    public = db.BooleanProperty(required=True)
    entitytype = db.StringProperty(required=True, choices=set(["text","file","alias"]), indexed=False)
    contenttype = db.StringProperty(indexed=False)    # textはたぶん必須
    templatefile = db.StringProperty(indexed=False)   # contenttype='text/html'の場合のみ使用することを想定
    encoding = db.StringProperty(indexed=False)    # textで指定できる（指定しなくてもいいけど）
    textcontent = db.TextProperty()    # textで使用/指定されたエンコードに変換したうえで参照
    blobcontent = db.BlobProperty()
    aliastarget = db.SelfReferenceProperty()    # aliasで使用
    lastupdate = db.DateTimeProperty()

class MainHandler(webapp.RequestHandler):
    def get(self):
        c=Content.get_by_key_name('e'+self.request.path[1:])
        if c and (c.public or users.is_current_user_admin()):
            if c.entitytype=='text':
                tc=c.textcontent
                tn=c.name
                if c.contenttype:
                    self.response.headers["Content-Type"]=c.contenttype
                    if c.encoding:
                        self.response.headers["Content-Type"]+="; charset="+c.encoding
                        tc=tc.encode(c.encoding)
                        tn=tn.encode(c.encoding)
                if c.templatefile:
                    path=os.path.join(os.path.dirname(__file__), c.templatefile)
                    self.response.out.write(template.render(path, {'name': tn, 'content': tc}))
                    return
                else:
                    self.response.out.write(tc)
                    return
            elif c.entitytype=='file':
                if c.contenttype:
                    self.response.headers["Content-Type"]=c.contenttype
                self.response.out.write(c.blobcontent)
                return
        self.error(404)

class ListHandler(webapp.RequestHandler):
    def get(self):
        if users.get_current_user():
            if users.is_current_user_admin():
                path = os.path.join(os.path.dirname(__file__), 'template_admin.html')
                q=Content.all()
                q.order('__key__')
                self.response.out.write(template.render(path, {'contents':q.fetch(1000,0),'CURRENT_PATH':LIST_PATH,'LIST_PATH':LIST_PATH,'EDIT_PATH':EDIT_PATH,'UPLOAD_PATH':UPLOAD_PATH}))
                return
        self.redirect(users.create_login_url(self.request.uri))

class EditHandler(webapp.RequestHandler):
    def get(self):
        if users.get_current_user():
            if users.is_current_user_admin():
                if self.request.arguments():
                    if self.request.get(u'mode')=='delete':
                        c=Content.get_by_key_name('e'+self.request.get(u'target')[1:])
                        if c:
                            c.delete()
                        self.redirect(LIST_PATH)
                        return
                    elif self.request.get(u'mode')=='modify':
                        c=Content.get_by_key_name('e'+self.request.get(u'target')[1:])
                        if c:
                            if c.entitytype=='file':
                                self.redirect(UPLOAD_PATH+'?target='+self.request.get('target'))
                                return
                        path = os.path.join(os.path.dirname(__file__), 'template_admin.html')
                        self.response.out.write(template.render(path, {'CURRENT_PATH':EDIT_PATH,'LIST_PATH':LIST_PATH,'EDIT_PATH':EDIT_PATH,'UPLOAD_PATH':UPLOAD_PATH,'modify':c}))
                        return
                path = os.path.join(os.path.dirname(__file__), 'template_admin.html')
                q = Content.all()
                q.order('__key__')
                self.response.out.write(template.render(path, {'contents':q.fetch(1000,0),'CURRENT_PATH':EDIT_PATH,'LIST_PATH':LIST_PATH,'EDIT_PATH':EDIT_PATH,'UPLOAD_PATH':UPLOAD_PATH}))
                return
        self.redirect(users.create_login_url(self.request.uri))
    def post(self):
        dtype = self.request.get('datatype')
        if dtype=='text':
            p = self.request.get('path')
            if p and p[0]=='/':
                p = p[1:]
            if p[0:4]=='_ah/' or p=='form' or p==LIST_PATH[1:] or p==EDIT_PATH[1:] or p==UPLOAD_PATH[1:]:
                self.redirect(LIST_PATH)
                return
            c=Content.get_by_key_name('e'+p)
            if c:
                c.public=(self.request.get('public') == 'on')
                c.entitytype='text'
                c.blobcontent=None
                c.aliastarget=None
            else:
                c=Content(key_name='e'+p,
                          path='/'+p,
                          public=(self.request.get('public') == 'on'),
                          entitytype='text')
            c.name=self.request.get('name')
            c.encoding=self.request.get('encoding')
            c.textcontent=self.request.get('content')
            mtype,stype=mimetypes.guess_type(c.path)
            if mtype:
                c.contenttype=str(mtype)
            else:
                c.contenttype='text/html'
            if c.contenttype=='text/html':
                c.templatefile='template.html'
            else:
                c.templatefile=None
            c.lastupdate=datetime.datetime.now()
            c.put()
        self.redirect(LIST_PATH)

class UploadHandler(webapp.RequestHandler):
    def get(self):
        if users.get_current_user():
            if users.is_current_user_admin():
                path = os.path.join(os.path.dirname(__file__), 'template_admin.html')
                if self.request.get('target'):
                    c=Content.get_by_key_name('e'+self.request.get('target')[1:])
                else:
                    c=None
                self.response.out.write(template.render(path, {'CURRENT_PATH':UPLOAD_PATH,'LIST_PATH':LIST_PATH,'EDIT_PATH':EDIT_PATH,'UPLOAD_PATH':UPLOAD_PATH,'modify':c}))
                return
        self.redirect(users.create_login_url(self.request.uri))
    def post(self):
        if users.get_current_user():
            if users.is_current_user_admin():
                fname=self.request.get('name')
                fpath=self.request.get('path')
                if fname and fpath:
                    if fpath and fpath[0]=='/':
                        fpath = fpath[1:]
                    if fpath=='_ah/' or fpath=='form' or fpath==LIST_PATH[1:] or fpath==EDIT_PATH[1:] or fpath==UPLOAD_PATH[1:]:
                        self.redirect(LIST_PATH)
                        return
                    c=Content.get_by_key_name('e'+fpath)
                    if c:
                        c.name=fname
                        c.public=(self.request.get('public') == 'on')
                        c.entitytype='file'
                        c.templatefile=None
                        c.encoding=None
                        c.textcontent=None
                        c.blobcontent=self.request.get('file')
                        c.aliastarget=None
                        c.lastupdate=datetime.datetime.now()
                    else:
                        c = Content(key_name='e'+fpath,
                                    name=fname,
                                    path='/'+fpath,
                                    public=(self.request.get('public') == 'on'),
                                    entitytype='file',
                                    blobcontent=self.request.get('file'),
                                    lastupdate=datetime.datetime.now())
                    mtype,stype=mimetypes.guess_type(c.path)
                    if mtype:
                        c.contenttype=str(mtype)
                    else:
                        c.contenttype=None
                    c.put()
                self.redirect(LIST_PATH)
                return
        self.redirect(users.create_login_url(self.request.uri))

def main():
    application = webapp.WSGIApplication([(LIST_PATH, ListHandler),
                                          (EDIT_PATH, EditHandler),
                                          (UPLOAD_PATH, UploadHandler),
                                          ('/.*', MainHandler)],
                                         debug=True)
    util.run_wsgi_app(application)

if __name__ == '__main__':
    main()
