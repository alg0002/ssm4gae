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

import datetime,os,urllib
from google.appengine.api import users,memcache
from google.appengine.dist import use_library
use_library('django','0.96')
from google.appengine.ext import db,webapp
from google.appengine.ext.webapp import blobstore_handlers,template,util

# Reserved path
LIST_PATH   ='/admin_listcontent'
EDIT_PATH   ='/admin_editcontent'
ALIAS_PATH  ='/admin_editalias'
UPLOAD_PATH ='/admin_uploadfile'
SETTING_PATH='/admin_setting'
# Directory Index
DIRECTORY_INDEX='index.html'
# Display count per page
COUNT_PER_PAGE=20
# Others
NO_NAME='(No name)'

class Content(db.Model):
    # key_name = 'e'+path
    name=db.StringProperty()
    public=db.BooleanProperty(required=True)
    entitytype=db.StringProperty(required=True, choices=set(["text","file","alias"]), indexed=False)
    contenttype=db.StringProperty(indexed=False)
    templatefile=db.StringProperty(indexed=False)
    encoding=db.StringProperty(indexed=False)
    textcontent=db.TextProperty()
    blobcontent=db.BlobProperty()
    aliastarget=db.StringProperty()
    description=db.TextProperty()
    lastupdate=db.DateTimeProperty(auto_now=True)
    path=db.StringProperty(required=True)
    parentpath=db.StringProperty()
    def setparentinfo(self):
        p=self.path
        if p.rfind('/')==-1:
            self.parentpath=''
        else:
            self.parentpath=p[0:p.rfind('/')]

class Setting(db.Model):
    # key_name = 'default'
    utcoffset=db.IntegerProperty(default=9)

class MainHandler(webapp.RequestHandler):
    def get(self):
        c=get_content(self.request.path)
        if c and (c.public or users.is_current_user_admin()):
            if c.entitytype=='text':
                if self.returntext(c):
                    return
            elif c.entitytype=='file':
                if self.returnfile(c):
                    return
            elif c.entitytype=='alias':
                if c.aliastarget and c.aliastarget.startswith('http://'):
                    from google.appengine.api import urlfetch
                    result=urlfetch.fetch(url=c.aliastarget)
                    self.response.headers["Content-Type"]=result.headers["Content-Type"]
                    self.response.out.write(result.content)
                    return
                else:
                    c=get_content(c.aliastarget)
                    if c and (c.public or users.is_current_user_admin()):
                        if c.entitytype=='text':
                            if self.returntext(c):
                                return
                        elif c.entitytype=='file':
                            if self.returnfile(c):
                                return
        self.error(404)
    def returntext(self,c):
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
            return True
        else:
            self.response.out.write(c.textcontent)
            return True
    def returnfile(self,c):
        b=c.blobcontent
        if c.contenttype:
            self.response.headers["Content-Type"]=c.contenttype
            w=self.request.get(u'w')
            h=self.request.get(u'h')
            if w.isdigit():
                w=int(w)
            else:
                w=0
            if h.isdigit():
                h=int(h)
            else:
                h=0
            if w>0 or h>0:
                from google.appengine.api import images
                img=images.Image(b)
                if w>0 and h>0:
                    img.resize(width=w,height=h)
                elif w>0:
                    img.resize(width=w)
                else:
                    img.resize(height=h)
                imgtypes={'image/jpeg':images.JPEG,
                          'image/png' :images.PNG,
#                          images.WEBP,
                          'image/bmp' :images.BMP,
                          'image/gif' :images.GIF,
                          'image/x-icon':images.ICO,
                          'image/tiff':images.TIFF,
                }
                b=img.execute_transforms(output_encoding=imgtypes[c.contenttype])
        self.response.out.write(b)
        return True

class ListHandler(webapp.RequestHandler):
    def get(self):
        if users.get_current_user():
            if users.is_current_user_admin():
                path=os.path.join(os.path.dirname(__file__), 'template_admin.html')
                q=Content.all()
                q.order('__key__')
                mp=int(float(q.count())/float(COUNT_PER_PAGE)+.99)
                if mp<1:
                    mp=1
                p=self.request.get(u'page')
                if not p or not p.isdigit():
                    p=1
                else:
                    p=int(p)
                    if p<1:
                        p=1
                    elif p>mp:
                        p=mp
                allpages=range(1,mp+1)
                if len(allpages)==1:
                    allpages=None
                self.response.out.write(template.render(path, {
                    'contents':q.fetch(COUNT_PER_PAGE,(p-1)*COUNT_PER_PAGE),
                    'CURRENT_PATH':LIST_PATH,
                    'LIST_PATH':LIST_PATH,
                    'EDIT_PATH':EDIT_PATH,
                    'UPLOAD_PATH':UPLOAD_PATH,
                    'ALIAS_PATH':ALIAS_PATH,
                    'SETTING_PATH':SETTING_PATH,
                    'currentpage':p,
                    'allpages':allpages
                }))
                return
        self.redirect(users.create_login_url(self.request.uri))

class EditHandler(webapp.RequestHandler):
    def get(self):
        if users.get_current_user():
            if users.is_current_user_admin():
                if self.request.arguments():
                    if self.request.get(u'mode')=='delete':
                        c=get_content(self.request.get(u'target'))
                        if c:
                            c.delete()
                        self.redirect(LIST_PATH)
                        return
                    elif self.request.get(u'mode')=='modify':
                        c=get_content(self.request.get(u'target'))
                        if c:
                            if c.entitytype=='file':
                                self.redirect(UPLOAD_PATH+'?target='+self.request.get('target'))
                                return
                            elif c.entitytype=='alias':
                                self.redirect(ALIAS_PATH+'?target='+self.request.get('target'))
                                return
                        errormsg=self.request.get(u'errormsg')
                        path=os.path.join(os.path.dirname(__file__), 'template_admin.html')
                        self.response.out.write(template.render(path, {'CURRENT_PATH':EDIT_PATH,'LIST_PATH':LIST_PATH,'EDIT_PATH':EDIT_PATH,'UPLOAD_PATH':UPLOAD_PATH,'ALIAS_PATH':ALIAS_PATH,'SETTING_PATH':SETTING_PATH,'modify':c,'errormsg':errormsg}))
                        return
                path=os.path.join(os.path.dirname(__file__), 'template_admin.html')
                q=Content.all()
                q.order('__key__')
                self.response.out.write(template.render(path, {'CURRENT_PATH':EDIT_PATH,'LIST_PATH':LIST_PATH,'EDIT_PATH':EDIT_PATH,'UPLOAD_PATH':UPLOAD_PATH,'ALIAS_PATH':ALIAS_PATH,'SETTING_PATH':SETTING_PATH}))
                return
        self.redirect(users.create_login_url(self.request.uri))
    def post(self):
        if users.get_current_user():
            if users.is_current_user_admin():
                dtype=self.request.get('datatype')
                if dtype=='text':
                    oldpath=self.request.get('oldpath')
                    if oldpath:
                        oldpath=convpath(oldpath)
                        oc=get_content(oldpath)
                        if oc:
                            oc.delete()
                    p=self.request.get('path')
                    p=convpath(p)
                    if p is None:
                        self.redirect(LIST_PATH)
                        return
                    elif p[len(p)-1]=='/':
                        p=p+DIRECTORY_INDEX
                    c=get_content(p)
                    if c:
                        c.delete()
                    c=Content(key_name='e'+p,
                              path=p,
                              public=(self.request.get('public') == 'on'),
                              entitytype='text')
                    c.name=self.request.get('name')
                    if not c.name:
                        c.name=NO_NAME
                    c.encoding=self.request.get('encoding')
                    c.textcontent=self.request.get('content')
                    import mimetypes
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
                    if not c.description:
                        c.description=''
                    c.setparentinfo()
                    c.put()
                self.redirect(LIST_PATH)
                return
        self.redirect(users.create_login_url(self.request.uri))

class UploadHandler(webapp.RequestHandler):
    def get(self):
        if users.get_current_user():
            if users.is_current_user_admin():
                path=os.path.join(os.path.dirname(__file__), 'template_admin.html')
                if self.request.get('target'):
                    c=get_content(self.request.get('target'))
                else:
                    c=None
                errormsg=self.request.get(u'errormsg')
                self.response.out.write(template.render(path, {'CURRENT_PATH':UPLOAD_PATH,'LIST_PATH':LIST_PATH,'EDIT_PATH':EDIT_PATH,'UPLOAD_PATH':UPLOAD_PATH,'ALIAS_PATH':ALIAS_PATH,'SETTING_PATH':SETTING_PATH,'modify':c,'errormsg':errormsg}))
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
                    elif fpath[len(fpath)-1]=='/':
                        fpath=fpath+DIRECTORY_INDEX
                    oldpath=self.request.get('oldpath')
                    if oldpath:
                        oldpath=convpath(oldpath)
                        oc=get_content(oldpath)
                        if oc:
                            if oc.blobcontent and not ffile:
                                ffile=oc.blobcontent
                            oc.delete()
                    c=get_content(fpath)
                    if c:
                        c.delete()
                    c=Content(key_name='e'+fpath,
                              name=fname,
                              path=fpath,
                              public=(self.request.get('public')=='on'),
                              entitytype='file',
                              blobcontent=ffile,
                              lastupdate=datetime.datetime.now())
                    if not c.name:
                        c.name=NO_NAME
                    import mimetypes
                    mtype,stype=mimetypes.guess_type(c.path)
                    if mtype:
                        c.contenttype=str(mtype)
                    else:
                        if c.path.endswith(".ico"):
                            c.contenttype="image/x-icon"
                        else:
                            c.contenttype=None
                    c.description=self.request.get('description')
                    if not c.description:
                        c.description=''
                    c.setparentinfo()
                    try:
                        from google.appengine.runtime import apiproxy_errors
                        c.put()
                    except apiproxy_errors.RequestTooLargeError:
                        c.blobcontent=None
                        c.put()
                        self.redirect(UPLOAD_PATH+'?target='+c.path+'&errormsg=Too%20large%20file')
                        return
                self.redirect(LIST_PATH)
                return
        self.redirect(users.create_login_url(self.request.uri))

class AliasHandler(webapp.RequestHandler):
    def get(self):
        if users.get_current_user():
            if users.is_current_user_admin():
                path=os.path.join(os.path.dirname(__file__), 'template_admin.html')
                if self.request.get('target'):
                    c=get_content(self.request.get('target'))
                else:
                    c=None
                self.response.out.write(template.render(path, {'CURRENT_PATH':ALIAS_PATH,'LIST_PATH':LIST_PATH,'EDIT_PATH':EDIT_PATH,'UPLOAD_PATH':UPLOAD_PATH,'ALIAS_PATH':ALIAS_PATH,'SETTING_PATH':SETTING_PATH,'modify':c}))
                return
        self.redirect(users.create_login_url(self.request.uri))
    def post(self):
        if users.get_current_user():
            if users.is_current_user_admin():
                dtype=self.request.get('datatype')
                if dtype=='alias':
                    oldpath=self.request.get('oldpath')
                    if oldpath:
                        oldpath=convpath(oldpath)
                        oc=get_content(oldpath)
                        if oc:
                            oc.delete()
                    p=self.request.get('path')
                    p=convpath(p)
                    if p is None:
                        self.redirect(ALIAS_PATH)
                        return
                    elif p[len(p)-1]=='/':
                        p=p+DIRECTORY_INDEX
                    c=get_content(p)
                    if c:
                        c.delete()
                    c=Content(key_name='e'+p,
                              path=p,
                              public=(self.request.get('public') == 'on'),
                              entitytype='alias')
                    c.name=self.request.get('name')
                    if not c.name:
                        c.name=NO_NAME
                    c.aliastarget=self.request.get('aliastarget')
                    c.description=self.request.get('description')
                    if not c.description:
                        c.description=''
                    c.setparentinfo()
                    c.put()
                self.redirect(LIST_PATH)
                return
        self.redirect(users.create_login_url(self.request.uri))

class SettingHandler(webapp.RequestHandler):
    def get(self):
        if users.get_current_user():
            if users.is_current_user_admin():
                s=get_setting()
                path=os.path.join(os.path.dirname(__file__), 'template_admin.html')
                self.response.out.write(template.render(path, {'CURRENT_PATH':SETTING_PATH,'LIST_PATH':LIST_PATH,'EDIT_PATH':EDIT_PATH,'UPLOAD_PATH':UPLOAD_PATH,'ALIAS_PATH':ALIAS_PATH,'SETTING_PATH':SETTING_PATH,'setting':s}))
                return
        self.redirect(users.create_login_url(self.request.uri))
    def post(self):
        if users.get_current_user():
            if users.is_current_user_admin():
                s=get_setting()
                s.utcoffset=int(self.request.get('utcoffset'))
                path=os.path.join(os.path.dirname(__file__), 'template_admin.html')
                self.response.out.write(template.render(path, {'CURRENT_PATH':SETTING_PATH,'LIST_PATH':LIST_PATH,'EDIT_PATH':EDIT_PATH,'UPLOAD_PATH':UPLOAD_PATH,'ALIAS_PATH':ALIAS_PATH,'SETTING_PATH':SETTING_PATH,'setting':s}))
                return
        self.redirect(users.create_login_url(self.request.uri))

def convpath(path):
    if not path or path[0]!='/':
        path='/'+path
    if path[0:5]=='/_ah/' or path=='/form' or path==LIST_PATH or path==EDIT_PATH or path==UPLOAD_PATH or path==ALIAS_PATH or path==SETTING_PATH:
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

def get_content(path):
    path=convpath(path)
    c=Content.get_by_key_name('e'+path)
    if c:
        return c
    else:
        if path[len(path)-1]=='/':
            c=Content.get_by_key_name('e'+path+DIRECTORY_INDEX)
            if c:
                return c
        if path[len(path)-1-len(DIRECTORY_INDEX):]=='/'+DIRECTORY_INDEX:
            c=Content.get_by_key_name('e'+path[0:len(path)-len(DIRECTORY_INDEX)])
            if c:
                return c

def main():
    application=webapp.WSGIApplication([(LIST_PATH, ListHandler),
                                        (EDIT_PATH, EditHandler),
                                        (UPLOAD_PATH, UploadHandler),
                                        (ALIAS_PATH, AliasHandler),
                                        (SETTING_PATH, SettingHandler),
                                        ('/.*', MainHandler)],
                                       debug=True)
    util.run_wsgi_app(application)

if __name__ == '__main__':
    main()
