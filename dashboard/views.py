from __future__ import unicode_literals
from django.shortcuts import render,redirect
from django.contrib.auth.decorators import login_required
from django.shortcuts import HttpResponseRedirect, HttpResponse
from django.contrib.auth import get_user
from django.conf import settings
import requests
import json
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import ChartMeta, DashboardWidgetSummaryLog
from mis.models import *
from django.db.models import Subquery
from django.http import JsonResponse
from django.db import connection
from django.utils.encoding import smart_str
from datetime import datetime
import calendar
import csv
from django.http import HttpResponseRedirect
from django.contrib.contenttypes.models import ContentType
import traceback
import sys
import logging

logger = logging.getLogger(__name__)


# #****************************************************************************
# # update stackabar chart data to replace dummy data with actual values
# #****************************************************************************


def set_column_stack_chart_data(sql, headers):
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        newdata = []
        newdata.append(headers)
        for row in rows:
            row_data = list(row)
            newdata.append(row_data)
            new_row_data = []
    finally:
        if cursor:
            cursor.close()
    return newdata


# #****************************************************************************
# # update column chart data  and labels to replace dummy data with actual values
# # labels only for dynamic bars - last 6 months kind of charts
# #****************************************************************************


def old_set_column_chart_data(sql, labels):
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        descr = cursor.description
        counter = 0
        data = []

        data = [dict(zip([column for column in labels], row))for row in rows]

        # all queries always return one row - even when no data exists
        row = rows[0]
    finally:
        if cursor:
            cursor.close()
    return data[0].items()

def set_column_chart_data(sql, labels): #, bar_colors):
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        counter = 0
        data = []
        header_row = labels
        #header_row.append({ 'role': 'annotation' })
        data.append(header_row)
        #all queries always return one row - even when no data exists
        for row in list(rows):
            row_data = []
            for item in row:
                row_data.append(item)
            #row_data.append(str(row_data[-1]))
            data.append(row_data)
        if len(data) == 1:
            dummy_data_row = [""]
            for x in range(1,len(labels)):
                dummy_data_row.append(0)
            data.append(dummy_data_row)
    finally:
        if cursor:
            cursor.close()
    return data


def set_bar_chart_dynamic_lable(sql):
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        descr = cursor.description
        data = []
        for i in rows:
            i = list(i)
            i[1] = int(i[1])
            data.append(i)
    finally:
        if cursor:
            cursor.close()
    return data

# #****************************************************************************
# # update table chart data to replace dummy data with actual values
# #****************************************************************************
def set_table_chart_data(sql, headers):
    cursor = connection.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()
    newdata = []
    newdata.append(headers)
    for row in rows:
        newdata.append(list(row))
    return newdata


# #****************************************************************************
# # Dashboard
# #****************************************************************************


@login_required(login_url='/login/')
def dashboard(request, slug):
    heading = "Dashboard"
    user = get_user(request)
    current_site = request.session.get('site_id')
    user_role = str(get_user(request).groups.last())
    district_list = request.session.get('user_district')
    block_ids = request.session.get('user_block')
    
    # district_list = Block.objects.all()
    
    # if (user_role == 'Cluster Coordinator'):
    #     user_report_cc = MisReport.objects.filter(report_person = request.user).distinct('report_person')
    # elif (user_role == 'Program Officer' or user_role == 'Trainging Coordinator'):
    #     user_report_cc = MisReport.objects.filter(report_to = request.user)
    # elif (user_role == 'Senior Program Officer'):
    #     user_report_po = MisReport.objects.filter(report_to = request.user)
    #     user_report_cc = MisReport.objects.filter(report_to__id__in = user_report_po)
    # elif (user_role == 'Senior Lead'):
    #     user_report_spo = MisReport.objects.filter(report_to = request.user)
    #     user_report_po = MisReport.objects.filter(report_to__id__in = user_report_spo)
    #     user_report_cc = MisReport.objects.filter(report_to__id__in = user_report_po)
    if (user_role == 'Cluster Coordinator'):
        user_report_cc = MisReport.objects.filter(report_person = request.user).values_list('report_person__id', flat=True).distinct('report_person')
    elif (user_role == 'Program Officer' or user_role == 'Trainging Coordinator'):
        user_report_cc = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    elif (user_role == 'Senior Program Officer'):
        user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person', flat=True)
        user_report_cc = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    elif (user_role == 'Senior Lead' or user_role == 'Admin'):
        user_report_spo = MisReport.objects.filter(report_to = request.user).values_list('report_person', flat=True)
        user_report_po = MisReport.objects.filter(report_to__id__in = user_report_spo).values_list('report_person', flat=True)
        user_report_cc = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    user_list_ids = [str(i) for i in user_report_cc]
    user_ids = User.objects.filter(id__in=user_list_ids).values('id','username').order_by('username')

    try:
        # slug = 'dashboard1'
        cht = ChartMeta.objects.filter(page_slug = slug,
            status=1).order_by('display_order')
        chart_list = []
        # states = filter_location_state(request)
        # selected_items = [request.POST.get('state', 0), request.POST.get(
        #     'district', 0), request.POST.get('shelter', 0)]
        # districts, shelterhome = None, None
        # if request.POST.get('state'):
        #     districts = filter_location_district(
        #         request, request.POST.get('state'))
        # elif states.count() == 1:
        #     districts = filter_location_district(
        #         request, states[0].id)
        # if request.POST.get('district'):
        #     shelterhome = filter_location_shelterhome(
        #         request, request.POST.get('district'),True)
        # elif districts and districts.count() == 1:
        #     shelterhome = filter_location_shelterhome(
        #         request, districts[0].id,True)
        # print(districts)
        req_list = request.POST.dict()
        bk_ids = request.POST.getlist('block')
        usr_ids = request.POST.getlist('user')
        dt_ids = request.POST.getlist('district')
        mat_view_last_updated = '' #DashboardWidgetSummaryLog.objects.get(status=2, log_key='mat_child_dashboard_view').last_successful_update
        logger.error("cht-len:"+ str(len(cht)))
        table_chart_addln_headers = {}
        filter_values = get_filter_values(request)
        for i in cht:
            if current_site != 2 and i.chart_slug in ['geography-digital-literacy','geography-digital-literacy-tabular']:
                continue
            filtered_query = apply_filter(i.chart_query.get('sql_query'), i.filter_info, filter_values)
            if i.chart_type == 1: #column Chart
                cht_info = {}
                labels = i.chart_query.get('labels')
                #update query here to replace the filter values
                chart_data = list(set_column_chart_data(filtered_query, labels))
                cht_info = {"chart_type": "COLUMNCHART"}
                cht_info["chart_title"] = i.chart_title
                cht_info["datas"] = chart_data
                cht_info["chart_slug"] = i.chart_slug
                cht_info.update({"options": i.chart_options})
                cht_info.update({"tooltip": i.chart_tooltip})
                cht_info.update({"chart_note": i.chart_note})
                cht_info.update({"chart_name": i.chart_slug})
                cht_info["chart_height"] = i.chart_height
                cht_info["addln_header"] = ""
                cht_info.update({"div": i.div_class})
                chart_list.append(cht_info)
            elif i.chart_type == 3: #Table Chart
                cht_info = {"chart_type": "TABLECHART"}
                headers = i.chart_query.get('col_headers')
                #filtered_query = apply_filter(request, i.chart_query.get('sql_query'), i.filter_info,filter_values)
                chart_data = set_table_chart_data(filtered_query, headers)
                cht_info["chart_slug"] = i.chart_slug
                cht_info["chart_title"] = i.chart_title
                cht_info["options"] = i.chart_options
                cht_info["datas"] = chart_data
                cht_info["tooltip"] = i.chart_tooltip
                cht_info["chart_height"] = i.chart_height
                cht_info["chart_name"] = i.chart_slug
                cht_info.update({"chart_note": i.chart_note})
                cht_info["div"] = i.div_class
                cht_info["addln_header"] = i.chart_query.get('addln_header','').strip()
                chart_list.append(cht_info)
            elif i.chart_type == 4 or i.chart_type == 6: # Bar chart
                cht_info = {}
                #filtered_query = apply_filter(request, i.chart_query.get('sql_query'),i.filter_info)
                if i.chart_type == 4:
                    chart_data = list(set_column_chart_data(filtered_query, i.chart_query.get('labels')))
                else:
                    chart_data = list(set_bar_chart_dynamic_lable(filtered_query))
                cht_info = {"chart_type": "BARCHART"}
                cht_info["chart_slug"] = i.chart_slug
                cht_info["chart_title"] = i.chart_title
                chart_data.insert(0, ('', ''))
                cht_info["datas"] = chart_data
                cht_info.update({"tooltip": i.chart_tooltip})
                cht_info.update({"options": i.chart_options})
                cht_info.update({"chart_note": i.chart_note})
                cht_info.update({"chart_name": i.chart_slug})
                cht_info["chart_height"] = i.chart_height
                cht_info["addln_header"] = ''
                cht_info.update({"div": i.div_class})
                chart_list.append(cht_info)

            elif i.chart_type == 5:
                cht_info = {"chart_type": "COLUMNSTACK"}
                #filtered_query = apply_filter(request, i.chart_query.get('sql_query'), i.filter_info)
                chart_data = set_column_stack_chart_data(filtered_query, i.chart_query.get('col_headers'))
                cht_info["chart_slug"] = i.chart_slug
                cht_info["chart_title"] = i.chart_title
                cht_info["datas"] = chart_data
                cht_info["options"] = i.chart_options
                # chart_type values: 1=Column Chart, 2=Pie Chart, 3=Table Chart , 4- Column Stack
                cht_info["chart_height"] = i.chart_height
                cht_info["addln_header"] = ''
                cht_info["chart_name"] = i.chart_slug
                cht_info["div"] = i.div_class
                cht_info.update({"tooltip": i.chart_tooltip})
                cht_info.update({"chart_note": i.chart_note})
                cht_info.update({"chart_name": i.chart_title})
                chart_list.append(cht_info)
            if i.chart_query.get('addln_header','').strip() != '':
                func_info = [i.chart_slug.replace('-','_'),i.chart_query.get('addln_header').strip()]
                table_chart_addln_headers.update({i.chart_slug:func_info})

        logger.error("chart_list-len:"+ str(len(chart_list)))
        data = {"chart": chart_list}
        data_html = data
        data = json.dumps(data)
        
        if dt_ids:
            blk_list = []
            [blk_list.append(list(i.keys())[0]) for i in block_ids]
            block_list = Block.objects.filter(id__in=blk_list,district_id__in=dt_ids).values('id', 'name')
        return render(request, 'dashboard/dashboard.html', locals())
    except KeyError:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        error_stack = repr(traceback.format_exception(
        exc_type, exc_value, exc_traceback))
        logger.error(error_stack)
        return redirect('/login/')

#get the user selected filter values from the request and also the user permissions based filter values 
def get_filter_values(request):
    from dateutil.relativedelta import relativedelta
    user_site = request.session['site_id'] if 'site_id' in request.session else None
    user = get_user(request)
    current_site = request.session.get('site_id')
    user_role = str(get_user(request).groups.last())
    district_list = request.session.get('user_district')
    district_to_block_mapping_list = request.session.get('user_district_block_mapping')
    selected_district_id = request.POST.getlist('district', '') 
    selected_block_id = request.POST.getlist('block', '')
    selected_user_id = request.POST.getlist('user', '')
    start_date = request.POST.get('start_filter', '')
    end_date = request.POST.get('end_filter', '')
    s_date = ''
    e_date = ''
    if start_date != '':
        s_date = start_date + '-01'
        e_date = end_date + '-01'
        sd_date= datetime.strptime(s_date, "%Y-%m-%d")
        ed_date= datetime.strptime(e_date, "%Y-%m-%d")
        ed_date = ed_date + relativedelta(months=1)
        s_date = sd_date.strftime("%Y-%m-%d")
        e_date = ed_date.strftime("%Y-%m-%d")
        # print()
    if (user_role == 'Cluster Coordinator'):
        user_report_cc = MisReport.objects.filter(report_person = request.user).values_list('report_person__id', flat=True).distinct('report_person')
    elif (user_role == 'Program Officer' or user_role == 'Trainging Coordinator'):
        user_report_cc = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    elif (user_role == 'Senior Program Officer'):
        user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person', flat=True)
        user_report_cc = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    elif (user_role == 'Senior Lead' or user_role == 'Admin'):
        user_report_spo = MisReport.objects.filter(report_to = request.user).values_list('report_person', flat=True)
        user_report_po = MisReport.objects.filter(report_to__id__in = user_report_spo).values_list('report_person', flat=True)
        user_report_cc = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    user_list_ids = [str(i) for i in user_report_cc]
    if selected_user_id:
        user_ids = selected_user_id
        user_ids = ','.join(user_ids)
    else:
        user_ids = ','.join(user_list_ids)
    if selected_district_id:
        district_ids = selected_district_id
        block_lists =[]
        for i in district_ids:
            append_id = district_to_block_mapping_list[i]
            block_lists.extend(append_id)
        district_ids = ','.join(district_ids)
    else:
        block_lists=[]
        [block_lists.extend(i) for i in district_to_block_mapping_list.values()]
        district_lists = list(district_to_block_mapping_list.keys())
        district_ids = ",".join(district_lists)
    if selected_block_id:  
        block_ids = selected_block_id
        block_ids = ','.join(block_ids)
    else:
        block_list_ids=[]
        for block in block_lists:
            for key, value in block.items():
                block_list_ids.append(key)
        block_ids = ','.join(block_list_ids)
    if user_site is None:
        logger.error("User Site not added in sesssion")
    filter_values = {"user_site":str(user_site), "district":district_ids, "block":block_ids, "username":user_ids, "start_date":s_date, "end_date":e_date}        
    return filter_values

def apply_filter(sql_query, filter_info, filter_values):
    filter_cond = filter_info['filter_cond']
    start_date_filter_value = filter_values.get('start_date', None) 
    end_date_filter_value = filter_values.get('end_date', None) 
    for key in filter_cond.keys():
        updated_cond = ''  
        filter_value = filter_values.get(key, None)
        #logger.error("key:" + key + ":" + start_date_filter_value)
        if filter_value != None and str(filter_value) != '':
            #updated_cond = filter_cond[key].replace('@@filter_value', filter_value)
            #else:
            updated_cond = filter_cond[key].replace('@@filter_value', filter_value)
        if start_date_filter_value and key.endswith('_date'): # in ["start_date","end_date"]:
            updated_cond = filter_cond[key]
            updated_cond = updated_cond.replace('@@start_date_filter_value', start_date_filter_value)
            updated_cond = updated_cond.replace('@@end_date_filter_value', end_date_filter_value)
        # logger.error('updated_cond:' + updated_cond)
        sql_query = sql_query.replace('@@'+key+'_filter', updated_cond)
    # logger.error('QUERY :' + sql_query)
    return sql_query

def get_block(request, district_id):
    if request.method == 'GET':
        district_to_block_mapping_list = request.session.get('user_district_block_mapping')
        blocks = district_to_block_mapping_list.get(district_id)
        result_set = []
        for block in blocks:
            (blk_id, block_name), = block.items()
            result_set.append(
                {'id': blk_id, 'name': block_name,})
        return HttpResponse(json.dumps(result_set))


        # print(district_to_block_mapping_list, '****')
    # dist =list(district_to_block_mapping_list.keys())
    # for dist_ids in dist:
    #     dist_id = int(dist_ids)
    #     # print(dist_id,"--------------------")
    # district_list = request.session.get('user_district')
    # for dist in district_list:
    #     dist_values = dist.keys()

