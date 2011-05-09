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
from google.appengine.api import users,memcache
from google.appengine.dist import use_library
use_library('django','0.96')
from google.appengine.ext import blobstore,db,webapp
from google.appengine.ext.webapp import blobstore_handlers,template,util

# �\��ς݃p�X
LIST_PATH  ='/admin_listcontent'
EDIT_PATH  ='/admin_editcontent'
UPLOAD_PATH='/admin_uploadfile'

class Content(db.Model):
    # key_name = 'e'+path
    name=db.StringProperty()
    path=db.StringProperty(required=True)
    public=db.BooleanProperty(required=True)
    entitytype=db.StringProperty(required=True, choices=set(["text","file","alias"]), indexed=False)
    contenttype=db.StringProperty(indexed=False)    # text�͂��Ԃ�K�{
    templatefile=db.StringProperty(indexed=False)   # contenttype='text/html'�̏ꍇ�̂ݎg�p���邱�Ƃ�z��
    encoding=db.StringProperty(indexed=False)    # text�Ŏw��ł���i�w�肵�Ȃ��Ă��������ǁj
    textcontent=db.TextProperty()    # text�Ŏg�p/�w�肳�ꂽ�G���R�[�h�ɕϊ����������ŎQ��
    blobcontent=db.BlobProperty()
    aliastarget=db.SelfReferenceProperty()    # alias�Ŏg�p
    description=db.TextProperty()
    lastupdate=db.DateTimeProperty()

class Setting(db.Model):
  utcoffset=db.IntegerProperty(default=9)

class MainHandler(webapp.RequestHandler):
    def get(self):
        c=Content.get_by_key_name('e'+self.request.path)
        if c and (c.public or users.is_current_user_admin()):
            if c.entitytype=='text':
                if c.contenttype:
                    self.response.headers["Content-Type"]=c.contenttype
                    if c.encoding:
                        self.response.headers["Content-Type"]+="; charset="+c.encoding
                if c.templatefile:
                    cname=c.name.encode(c.encoding)
                    ctext=c.textcontent.encode(c.encoding)
                    cdesc=c.description.encode(c.encoding)
                    clast=c.lastupdate
                    s=get_setting()
                    clast+=datetime.timedelta(hours=s.utcoffset)
                    path=os.path.join(os.path.dirname(__file__), c.templatefile)
                    self.response.out.write(template.render(path, {'name':cname,'text':ctext,'description':cdesc,'lastupdate':clast}))
                    return
                else:
                    self.response.out.write(c.textcontent)
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
                path=os.path.join(os.path.dirname(__file__), 'template_admin.html')
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
                        c=Content.get_by_key_name('e'+self.request.get(u'target'))
                        if c:
                            c.delete()
                        self.redirect(LIST_PATH)
                        return
                    elif self.request.get(u'mode')=='modify':
                        c=Content.get_by_key_name('e'+self.request.get(u'target'))
                        if c:
                            if c.entitytype=='file':
                                self.redirect(UPLOAD_PATH+'?target='+self.request.get('target'))
                                return
                        path=os.path.join(os.path.dirname(__file__), 'template_admin.html')
                        self.response.out.write(template.render(path, {'CURRENT_PATH':EDIT_PATH,'LIST_PATH':LIST_PATH,'EDIT_PATH':EDIT_PATH,'UPLOAD_PATH':UPLOAD_PATH,'modify':c}))
                        return
                path=os.path.join(os.path.dirname(__file__), 'template_admin.html')
                q=Content.all()
                q.order('__key__')
                self.response.out.write(template.render(path, {'contents':q.fetch(1000,0),'CURRENT_PATH':EDIT_PATH,'LIST_PATH':LIST_PATH,'EDIT_PATH':EDIT_PATH,'UPLOAD_PATH':UPLOAD_PATH}))
                return
        self.redirect(users.create_login_url(self.request.uri))
    def post(self):
        dtype=self.request.get('datatype')
        if dtype=='text':
            oldpath=self.request.get('oldpath')
            if oldpath:
                oldpath=convpath(oldpath)
                oc=Content.get_by_key_name('e'+oldpath)
                if oc:
                    oc.delete()
            p=self.request.get('path')
            p=convpath(p)
            if p is None:
                self.redirect(LIST_PATH)
                return
            c=Content.get_by_key_name('e'+p)
            if c:
                c.delete()
            c=Content(key_name='e'+p,
                      path=p,
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
            c.description=self.request.get('description')
            c.lastupdate=datetime.datetime.now()
            c.put()
        self.redirect(LIST_PATH)

class UploadHandler(webapp.RequestHandler):
    def get(self):
        if users.get_current_user():
            if users.is_current_user_admin():
                path=os.path.join(os.path.dirname(__file__), 'template_admin.html')
                if self.request.get('target'):
                    c=Content.get_by_key_name('e'+self.request.get('target'))
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
                ffile=self.request.get('file')
                if fname and fpath:
                    fpath=convpath(fpath)
                    if fpath is None:
                        self.redirect(LIST_PATH)
                        return
                    oldpath=self.request.get('oldpath')
                    if oldpath:
                        oldpath=convpath(oldpath)
                        oc=Content.get_by_key_name('e'+oldpath)
                        if oc:
                            if oc.blobcontent and not ffile:
                                ffile=oc.blobcontent
                            oc.delete()
                    c=Content.get_by_key_name('e'+fpath)
                    if c:
                        c.delete()
                    c=Content(key_name='e'+fpath,
                              name=fname,
                              path=fpath,
                              public=(self.request.get('public')=='on'),
                              entitytype='file',
                              blobcontent=ffile,
                              lastupdate=datetime.datetime.now())
                    mtype,stype=mimetypes.guess_type(c.path)
                    if mtype:
                        c.contenttype=str(mtype)
                    else:
                        c.contenttype=None
                    c.description=self.request.get('description')
                    c.put()
                self.redirect(LIST_PATH)
                return
        self.redirect(users.create_login_url(self.request.uri))

def convpath(path):
    if not path or path[0]!='/':
        path='/'+path
    if path[0:5]=='/_ah/' or path=='/form' or path==LIST_PATH or path==EDIT_PATH or path==UPLOAD_PATH:
        return None
    return path

def get_setting():
    s=memcache.get('default_setting')
    if not s:
        s=Setting.get_by_key_name('default')
        if not s:
            s=Setting(key_name='default')
            s.put()
        memcache.set(key='default_setting',value=s,time=3600)
    return s

def main():
    application=webapp.WSGIApplication([(LIST_PATH, ListHandler),
                                        (EDIT_PATH, EditHandler),
                                        (UPLOAD_PATH, UploadHandler),
                                        ('/.*', MainHandler)],
                                       debug=True)
    util.run_wsgi_app(application)

if __name__ == '__main__':
    main()
