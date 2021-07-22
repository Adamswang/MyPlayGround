from django.db import models


#class Article (models.Model):
 #   title = models.CharField(max_length=60, default='title')
  #  content = models.TextField(null=True)


class Student (models.Model):
    id = models.BigIntegerField
    name = models.CharField(max_length=20, default='a')
    age = models.CharField(max_length=4, default='0')






# Create your models here.
