import json

import django
from application_masters.models import *
from mis.models import *
from django import template
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site

register = template.Library()

@register.filter(name='has_group')
def has_group(user, group_name):
    return user.groups.filter(name=group_name).exists()

@register.filter(name='current_domain')
def current_domain(user):
    user_id = UserSiteMapping.objects.filter(user__username=user).values_list('site', flat=True)
    user_site_id =list(user_id)[0]
    return user_site_id




