from django.conf.urls import url
from django.contrib import admin
from django.urls import path, include

from . import views

app_name = 'trump'
urlpatterns = [
    path(r'index', views.index, name='index'),
    path(r'search/<str:column>/<str:kw>', views.search, name='search'),
    path(r'export/<str:type>', views.export, name='export'),
    path(r'query', views.query, name='query')
]



