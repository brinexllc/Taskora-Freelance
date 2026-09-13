"""Attach Taskora workflow pages without replacing existing Django model routes."""
from types import MethodType
from functools import wraps
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import path
from rest_framework.exceptions import APIException
from . import views


def configure_admin_site(site):
    if getattr(site,'taskora_configured',False):return
    site.taskora_configured=True
    original_urls=site.get_urls
    original_context=site.each_context
    original_admin_view=site.admin_view
    def safe(view):
        @wraps(view)
        def guarded(request,*args,**kwargs):
            try:
                return view(request,*args,**kwargs)
            except (APIException,DjangoValidationError) as exc:
                message=str(getattr(exc,'detail',exc))
                response=views.render(request,'error.html',title='Действие недоступно',
                    error=message,message=message,status=getattr(exc,'status_code',400),back_url='/admin/control/security/')
                response.status_code=getattr(exc,'status_code',400)
                return response
        return guarded
    site.admin_view=MethodType(lambda self,view,cacheable=False: original_admin_view(safe(view),cacheable=cacheable),site)
    def each_context(self,request):
        from .query import NAV
        from django.conf import settings
        result=original_context(request)
        result.update(admin_nav=[{'key':key,'label':label,'icon':icon,'url':url,'active':request.path==url} for key,label,icon,url in NAV],
            environment={'local':'Локальная среда','test':'Тестовая среда','staging':'Тестовый стенд','production':'Production'}.get(settings.TASKORA_ENV,settings.TASKORA_ENV))
        return result
    def urls(self):
        view=self.admin_view
        return [
            path('control/search/',view(views.global_search),name='control-search'),
            path('control/security/',view(views.security_page),name='control-security'),
            path('control/new/<slug:kind>/',view(views.create),name='control-create'),
            path('control/files/<slug:kind>/<int:pk>/',view(views.private_file),name='control-file'),
            path('control/resolve/<uuid:pk>/',view(views.resolve_preview),name='control-resolve'),
            path('control/publish/<int:pk>/',view(views.publish_content),name='control-publish'),
            path('control/announcements/<int:pk>/',view(views.announcement),name='control-announcement'),
            path('control/exports/<uuid:pk>/',view(views.export_download),name='control-export'),
            path('control/<slug:resource>/<str:pk>/action/<str:action>/',view(views.command),name='control-command'),
            path('control/<slug:resource>/<str:pk>/',view(views.detail),name='control-detail'),
            path('control/<slug:resource>/',view(views.listing),name='control-list'),
        ]+original_urls()
    site.each_context=MethodType(each_context,site)
    site.get_urls=MethodType(urls,site)
    site.index=views.overview
    site.site_header='Taskora'
    site.site_title='Администрирование Taskora'
    site.index_title='Обзор платформы'
    site.enable_nav_sidebar=False
