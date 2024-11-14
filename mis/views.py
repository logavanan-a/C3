import json
from datetime import date
from dateutil.relativedelta import relativedelta
from django.contrib.auth import authenticate, get_user, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.sites.shortcuts import get_current_site
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.template.defaultfilters import slugify
from django.utils import timezone
from django.utils.timezone import localtime
from django.db import connection
from mis.models import *
from dashboard.models import *
import csv

def SqlHeader(query):
    cursor = connection.cursor()
    cursor.execute(query)
    descr = cursor.description
    rows = cursor.fetchall()
    data = [dict(zip([column[0] for column in descr], row)) for row in rows]
    # print("------------------\n\n\n"+sql)
    return data
    
# content_type__model=("awc", "school"), object_id=request.user.id
# Create your views here.

def getData(request):
    """ Get Data of subdomain """
    subDomain = request.META['HTTP_HOST'].lower().split('.')
    i = 0
    if subDomain[0] == 'www':
        i = (i + 1)
    codeobj = slugify(subDomain[i])

    try:
        site_obj = Site.objects.get(name = codeobj).domain
    except:
        site_obj = None
    return site_obj

def pagination_function(request, data):
    records_per_page = 10
    paginator = Paginator(data, records_per_page)
    page = request.GET.get('page', 1)
    try:
        pagination = paginator.page(page)
    except PageNotAnInteger:
        pagination = paginator.page(1)
    except EmptyPage:
        pagination = paginator.page(paginator.num_pages)
    return pagination

def login_view(request):
    heading = "Login"
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        data = getData(request)
        if UserSiteMapping.objects.filter(user__username = username, site__domain = data).exists():

            try:
                findUser = User._default_manager.get(username__iexact=username)
            except User.DoesNotExist:
                findUser = None
            if findUser is not None:
                username = findUser.get_username()
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                current_site = Site.objects.get(domain=request.META['HTTP_HOST'])
                request.session['site_id'] = current_site.id
                user_role = str(get_user(request).groups.last())
                if (user_role == 'Senior Lead' or user_role == 'Admin' or user_role == 'Reports'):
                    user_report_spo_to_sl = MisReport.objects.filter(report_to = user).values_list('report_person__id', flat=True)
                    user_report_po_to_spo = MisReport.objects.filter(report_to__id__in = user_report_spo_to_sl).values_list('report_person__id', flat=True)
                    cc_user_list = MisReport.objects.filter(report_to__id__in = user_report_po_to_spo).values_list('report_person__id', flat=True)
                elif (user_role == 'Senior Program Officer'):
                    user_report_po_to_spo = MisReport.objects.filter(report_to = user).values_list('report_person__id', flat=True)
                    cc_user_list = MisReport.objects.filter(report_to__id__in = user_report_po_to_spo).values_list('report_person__id', flat=True)
                elif (user_role == 'Program Officer' or user_role == 'Trainging Coordinator'):
                    cc_user_list = MisReport.objects.filter(report_to = user).values_list('report_person__id', flat=True)
                elif (user_role == 'Cluster Coordinator'):
                    cc_user_list = [user.id]
                if len(cc_user_list) >= 1:    
                    awc_ah_villages = CC_AWC_AH.objects.filter(status=1, user__id__in=cc_user_list).values_list('awc__village__id', flat=True)
                    awc_dl_villages = []
                    if current_site.id == 2:
                        # id 2 is fossil site. digital literacy(DL) only use in fossil
                        awc_dl_villages = CC_AWC_DL.objects.filter(status=1, user__id__in=cc_user_list).values_list('awc__village__id', flat=True)
                    school_villages = CC_School.objects.filter(status=1, user__id__in=cc_user_list).values_list('school__village__id', flat=True)

                    village_list = list(awc_ah_villages) + list(school_villages)# + list(awc_dl_villages) 
                    user_block_data = Village.objects.filter(status=1, id__in=village_list).values_list('grama_panchayat__block__district__id', 'grama_panchayat__block__district__name','grama_panchayat__block__id', 'grama_panchayat__block__name').distinct()
                #print(block_id, 'block_id')
                district_dict = {}
                district_list = []
                block_list =[]
                for blk in user_block_data:
                    blk_info = {str(blk[2]):blk[3]}
                    dst_data = district_dict.get(str(blk[0]),[])
                    if blk_info not in dst_data:
                        dst_data.append(blk_info)
                    district_dict.update({str(blk[0]):dst_data})
                    dst_info = {str(blk[0]):blk[1]}
                    if dst_info not in district_list:
                        district_list.append({str(blk[0]):blk[1]})
                    if blk_info not in block_list:
                        block_list.append(blk_info)
                #districts = [{i.id: i.name} for i in District.objects.filter(id__in=district_id)]
                #blocks = [{i.id: i.name} for i in Block.objects.filter(id__in=block_id)]
                request.session['user_district'] = district_list
                request.session['user_block'] = block_list
                request.session['user_district_block_mapping'] = district_dict
                if (user_role == 'Senior Lead'):
                    return HttpResponseRedirect('/spo/monthly/report/')
                elif (user_role == 'Admin'):
                    return HttpResponseRedirect('/dashboard1/')
                elif (user_role == 'Reports'):
                    return HttpResponseRedirect('/report_list/')
                else:
                    return HttpResponseRedirect('/monthly/report/')
            else:
                logout(request)
                error_message = "Invalid Username and Password"

        else:
            logout(request)
            error_message = "Do not have access"
    return render(request, 'dashboard/login.html', locals())

from django.views.decorators.csrf import csrf_exempt
@csrf_exempt 
def task_status_changes(request, task_id):
    if request.method == "POST":
        status_val = request.POST.get('status_val')
        remark = request.POST.get('remark')
        task_obj = Task.objects.get(id = task_id)
        task_obj.task_status = status_val
        task_obj.save()
        if remark:
            DataEntryRemark.objects.create(task = task_obj, remark = remark, user_name = request.user)
        return HttpResponse({"message":'true'} , content_type="application/json")
    return HttpResponse({"message":'false'}, content_type="application/json")  

@ login_required(login_url='/login/')
def adolescent_clinical_report(request):
    heading="Adolescent location mapping wise report"
    user = get_user(request)
    current_site = request.session.get('site_id')
    user_role = str(user.groups.last())
    user_site_ids = UserSiteMapping.objects.filter(site=current_site).values_list('user__id', flat=True)
    user_ids = User.objects.filter(id__in=user_site_ids, groups__id=1).order_by('username')
    filter_values = request.GET.dict()
    export=filter_values.get('export')
    filter_values_ids={}
    district_obj=request.session.get('user_district')
    district_to_block_mapping_list = request.session.get('user_district_block_mapping')
    district = request.GET.getlist('district', '')
    block = request.GET.getlist('block', '')
    grama_panchayat = request.GET.getlist('grama_panchayat', '')
    village = request.GET.getlist('village', '')
    awc = request.GET.getlist('awc', '')
    user = request.GET.getlist('user', '')
    filter_values_ids.update({'user': user,'district':district, 'block':block, 'grama_panchayat': grama_panchayat, 'village':village, 'awc':awc, 'export':export})
    district_ids = ','.join(district)
    block_ids = ','.join(block)
    grama_panchayat_ids = ','.join(grama_panchayat)
    village_ids = ','.join(village)
    awc_ids = ','.join(awc)
    usr_ids = ','.join(user)
    dst_id=""
    if district:
        dst_id = f'''and dst_id in ('''+district_ids+''')'''
        district_ids = district
        block_lists =[]
        for i in district_ids:
            append_id = district_to_block_mapping_list[i]
            block_lists.extend(append_id)
    blk_id=""
    if block:
        blk_id = f'''and blk_id in ('''+block_ids+''')'''
        grama_panchayat_obj = GramaPanchayat.objects.filter(block__id__in=block)
    pyt_id=""
    if grama_panchayat:
        pyt_id = f'''and pyt_id in ('''+grama_panchayat_ids+''')'''
        village_obj = Village.objects.filter(grama_panchayat__id__in=grama_panchayat)
    vlg_id=""
    if village:
        vlg_id = f'''and vlg_id in ('''+village_ids+''')'''
        awc_obj = AWC.objects.filter(village__id__in=village)
    awc_id=""
    if awc:
        awc_id = f'''and awc_id in ('''+awc_ids+''')'''
    cc_id=""
    if user:
        cc_id = f'''and cc_id in ('''+usr_ids+''')'''

    SqlHeader('''select adolescent_report()''')
    query=f'''select * from adolescent_temp where site_id={current_site} {dst_id} {blk_id} {pyt_id} {vlg_id} {awc_id} {cc_id}'''
    adolescen_clinic_data=SqlHeader(query)
    if export == 'adolescent_list':
        export_flag = 'adolescent_list' if request.GET.get('export') and request.GET.get('export').lower() == 'adolescent_list' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Adolescent list '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Adolescent ID',
                'District',
                'Block',
                'Panchayat',
                'Village',
                'Name of CC',
                'Anganwadi Center Code',
                'Anganwadi Center',
                'Adolescent',
                'Gender',
                'Age',
                'Date of Enrollment',
                'Life Skill/Day-1',#1
                'Life Skill/Day-2',
                'Life Skill/Day-3',
                'Learn and understand from peers/Day-1',#2
                'Learn and understand from peers/Day-2',
                'Learn and understand from peers/Day-3',
                'Communicate with confidence/Day-1',#3
                'Communicate with confidence/Day-2',
                'Communicate with confidence/Day-3',
                'Education is our right/Day-1',#4
                'Education is our right/Day-2',
                'Education is our right/Day-3',
                'Opportunity of skill development and employment/Day-1',#5
                'Opportunity of skill development and employment/Day-2',
                'Opportunity of skill development and employment/Day-3',
                "Let's go to Yuva Maitri Kendra-Police is at our service/Day-1",#6
                "Let's go to Yuva Maitri Kendra-Police is at our service/Day-2",
                "Let's go to Yuva Maitri Kendra-Police is at our service/Day-3",
                'Be careful about migration/Day-1',#7
                'Be careful about migration/Day-2',
                'Be careful about migration/Day-3',
                'Be careful when connected in internet/Day-1',#8
                'Be careful when connected in internet/Day-2',
                'Be careful when connected in internet/Day-3',
                'Sathiya Salah App is for us/Day-1',#9
                'Sathiya Salah App is for us/Day-2',
                'Sathiya Salah App is for us/Day-3',
                'Gender & Sex/Day-1',#10
                'Gender & Sex/Day-2',
                'Gender & Sex/Day-3',
                'Patriarchy -understanding relevent thinking & explanations/Day-1',#11
                'Patriarchy -understanding relevent thinking & explanations/Day-2',
                'Patriarchy -understanding relevent thinking & explanations/Day-3',
                'Why a son not a daughter?/Day-1',#12
                'Why a son not a daughter?/Day-2',
                'Why a son not a daughter?/Day-3',
                'Hum Barabar Tum Barabar, Gender Power Walk/Day-1',#13
                'Hum Barabar Tum Barabar, Gender Power Walk/Day-2',
                'Hum Barabar Tum Barabar, Gender Power Walk/Day-3',
                'Gender based violence/Day-1',#14
                'Gender based violence/Day-2',
                'Gender based violence/Day-3',
                'Understand and prevent gender based violance/Day-1',#15
                'Understand and prevent gender based violance/Day-2',
                'Understand and prevent gender based violance/Day-3',
                'Be aware of Human trafficking/Day-1',#16
                'Be aware of Human trafficking/Day-2',
                'Be aware of Human trafficking/Day-3',
                'Men should understand their roles and responsibility on gender equality/Day-1',#17
                'Men should understand their roles and responsibility on gender equality/Day-2',
                'Men should understand their roles and responsibility on gender equality/Day-3',
                'Child marriage, Dowry system, Witch system/Day-1',#18
                'Child marriage, Dowry system, Witch system/Day-2',
                'Child marriage, Dowry system, Witch system/Day-3',
                'Legal provisions related to Child marriage, Dowry system, Witch system/Day-1',#19
                'Legal provisions related to Child marriage, Dowry system, Witch system/Day-2',
                'Legal provisions related to Child marriage, Dowry system, Witch system/Day-3',
                'Causes of influencing nutrition & Anaemia/Day-1',#20
                'Causes of influencing nutrition & Anaemia/Day-2',
                'Causes of influencing nutrition & Anaemia/Day-3',
                'Personal hygiene/Day-1',#21
                'Personal hygiene/Day-2',
                'Personal hygiene/Day-3',
                'Adolescence/Day-1',#22
                'Adolescence/Day-2',
                'Adolescence/Day-3',
                'Adolescence - physical change/Day-1',#23
                'Adolescence - physical change/Day-2',
                'Adolescence - physical change/Day-3',
                'Adolescence - emotional change/Day-1',#24
                'Adolescence - emotional change/Day-2',
                'Adolescence - emotional change/Day-3',
                'Adolescence - social change/Day-1',#25
                'Adolescence - social change/Day-2',
                'Adolescence - social change/Day-3',
                'Developing positive attitude towards changes during adolescence/Day-1',#26
                'Developing positive attitude towards changes during adolescence/Day-2',
                'Developing positive attitude towards changes during adolescence/Day-3',
                'Adolescent reproductive organs and their functions/Day-1',#27
                'Adolescent reproductive organs and their functions/Day-2',
                'Adolescent reproductive organs and their functions/Day-3',
                'Menstruation & night fall/Day-1',#28
                'Menstruation & night fall/Day-2',
                'Menstruation & night fall/Day-3',
                'RTI/STI/Day-1',#29
                'RTI/STI/Day-2',
                'RTI/STI/Day-3',
                'HIV-AIDS/Day-1',#30
                'HIV-AIDS/Day-2',
                'HIV-AIDS/Day-3',
                'Contraception & Family Planning, teen pregnancy/Day-1',#31
                'Contraception & Family Planning, teen pregnancy/Day-2',
                'Contraception & Family Planning, teen pregnancy/Day-3',
                'Safe sex & legal age for consentual sex/Day-1',#32
                'Safe sex & legal age for consentual sex/Day-2',
                'Safe sex & legal age for consentual sex/Day-3',
                'We get healthy mind/Day-1',#33
                'We get healthy mind/Day-2',
                'We get healthy mind/Day-3',
                'Myth & Misconception regarding addictive substance among adolescents/Day-1',#34
                'Myth & Misconception regarding addictive substance among adolescents/Day-2',
                'Myth & Misconception regarding addictive substance among adolescents/Day-3',
                'Lifestyle and non-communicable diseases/Day-1',#35
                'Lifestyle and non-communicable diseases/Day-2',
                'Lifestyle and non-communicable diseases/Day-3',
                'Others/Day-1',#36
                'Others/Day-2',
                'Others/Day-3',
                'Total Number of Sessions attended',
                '%age of session attend',
                ])
            for data in adolescen_clinic_data:
                writer.writerow([
                    data['adolesent_code'],
                    data['dst_name'],
                    data['blk_name'],
                    data['pyt_name'],
                    data['vlg_name'],
                    data['cc_name'],
                    data['awc_code'],
                    data['awc_name'],
                    data['adolesent_name'],
                    data['gender'],
                    data['age'],
                    data['emt_date'],
                    data['life_skill_d1'],#1
                    data['life_skill_d2'],
                    data['life_skill_d3'],
                    data['lup_d1'],#2
                    data['lup_d2'],
                    data['lup_d3'],
                    data['cwc_d1'],#3
                    data['cwc_d2'],
                    data['cwc_d3'],
                    data['eor_d1'],#4
                    data['eor_d2'],
                    data['eor_d3'],
                    data['osd_d1'],#5
                    data['osd_d2'],
                    data['osd_d3'],
                    data['ymkp_d1'],#6
                    data['ymkp_d2'],
                    data['ymkp_d3'],
                    data['bciam_d1'],#7
                    data['bciam_d2'],
                    data['bciam_d3'],
                    data['bcci_d1'],#8
                    data['bcci_d2'],
                    data['bcci_d3'],
                    data['ssafu_d1'],#9
                    data['ssafu_d2'],
                    data['ssafu_d3'],
                    data['gs_d1'],#10
                    data['gs_d2'],
                    data['gs_d3'],
                    data['purt_d1'],#11
                    data['purt_d2'],
                    data['purt_d3'],
                    data['wsnd_d1'],#12
                    data['wsnd_d2'],
                    data['wsnd_d3'],
                    data['htgpw_d1'],#13
                    data['htgpw_d2'],
                    data['htgpw_d3'],
                    data['gbv_d1'],#14
                    data['gbv_d2'],
                    data['gbv_d3'],
                    data['uspgbv_d1'],#15
                    data['uspgbv_d2'],
                    data['uspgbv_d3'],
                    data['bwht_d1'],#16
                    data['bwht_d2'],
                    data['bwht_d3'],
                    data['murgq_d1'],#17
                    data['murgq_d2'],
                    data['murgq_d3'],
                    data['cm_dwsys_d1'],#18
                    data['cm_dwsys_d2'],
                    data['cm_dwsys_d3'],
                    data['dws_d1'],#19
                    data['dws_d2'],
                    data['dws_d3'],
                    data['cina_d1'],#20
                    data['cina_d2'],
                    data['cina_d3'],
                    data['ph_d1'],#21
                    data['ph_d2'],
                    data['ph_d3'],
                    data['adolesence_d1'],#22
                    data['adolesence_d2'],
                    data['adolesence_d3'],
                    data['apc_d1'],#23
                    data['apc_d2'],
                    data['apc_d3'],
                    data['aec_d1'],#24
                    data['aec_d2'],
                    data['aec_d3'],
                    data['asc_d1'],#25
                    data['asc_d2'],
                    data['asc_d3'],
                    data['dptcda_d1'],#26
                    data['dptcda_d2'],
                    data['dptcda_d3'],
                    data['arof_d1'],#27
                    data['arof_d2'],
                    data['arof_d3'],
                    data['mnf_d1'],#28
                    data['mnf_d2'],
                    data['mnf_d3'],
                    data['rti_sti_d1'],#29
                    data['rti_sti_d2'],
                    data['rti_sti_d3'],
                    data['hiv_aids_d1'],#30
                    data['hiv_aids_d2'],
                    data['hiv_aids_d3'],
                    data['cfp_d1'],#31
                    data['cfp_d2'],
                    data['cfp_d3'],
                    data['slafcs_d1'],#32
                    data['slafcs_d2'],
                    data['slafcs_d3'],
                    data['wghm_d1'],#33
                    data['wghm_d2'],
                    data['wghm_d3'],
                    data['mmrasna_d1'],#34
                    data['mmrasna_d2'],
                    data['mmrasna_d3'],
                    data['lncd_d1'],#35
                    data['lncd_d2'],
                    data['lncd_d3'],
                    data['other_d1'],#36
                    data['other_d2'],
                    data['other_d3'],
                    data['total'],
                    data['ptg'],
                    ])
            return response
    data = pagination_function(request, adolescen_clinic_data)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'reports/adolescent_clinic_leve.html', locals())

@ login_required(login_url='/login/')
def location_mapping_adolescent_data(request):
    heading="Adolescent Mapping report"
    user = get_user(request)
    current_site = request.session.get('site_id')
    user_role = str(user.groups.last())
    user_site_ids = UserSiteMapping.objects.filter(site=current_site).values_list('user__id', flat=True)
    user_ids = User.objects.filter(id__in=user_site_ids, groups__id=1).order_by('username')
    filter_values = request.GET.dict()
    export=filter_values.get('export')
    filter_values_ids={}
    district_obj=request.session.get('user_district')
    district_to_block_mapping_list = request.session.get('user_district_block_mapping')
    district = request.GET.getlist('district', '')
    block = request.GET.getlist('block', '')
    grama_panchayat = request.GET.getlist('grama_panchayat', '')
    village = request.GET.getlist('village', '')
    awc = request.GET.getlist('awc', '')
    user = request.GET.getlist('user', '')
    age = request.GET.get('age')
    filter_values_ids.update({'user': user, 'district':district, 'block':block, 'grama_panchayat': grama_panchayat, 'village':village, 'awc':awc, 'age': age, 'export':export,})
    district_ids = ','.join(district)
    block_ids = ','.join(block)
    grama_panchayat_ids = ','.join(grama_panchayat)
    village_ids = ','.join(village)
    awc_ids = ','.join(awc)
    usr_ids = ','.join(user)
    dst_id=""
    if district:
        dst_id = f'''and district_id in ('''+district_ids+''')'''
        district_ids = district
        block_lists =[]
        for i in district_ids:
            append_id = district_to_block_mapping_list[i]
            block_lists.extend(append_id)
    blk_id=""
    if block:
        blk_id = f'''and block_id in ('''+block_ids+''')'''
        grama_panchayat_obj = GramaPanchayat.objects.filter(block__id__in=block)
    pyt_id=""
    if grama_panchayat:
        pyt_id = f'''and gp.id in ('''+grama_panchayat_ids+''')'''
        village_obj = Village.objects.filter(grama_panchayat__id__in=grama_panchayat)
    vlg_id=""
    if village:
        vlg_id = f'''and village_id in ('''+village_ids+''')'''
        awc_obj = AWC.objects.filter(village__id__in=village)
    awc_id=""
    if awc:
        awc_id = f'''and awc.id in ('''+awc_ids+''')'''
    cc_id=""
    if user:
        cc_id = f'''and au.id in ('''+usr_ids+''')'''
    if age == "2":
        age_range = f'''and adl.age_in_completed_years > 19''' 
    else:
        age_range = f'''and adl.age_in_completed_years >= 10 and adl.age_in_completed_years <= 19''' 
    query=f'''SELECT au.id as user_id, au.username as username, adl.id as adolescent_id,adl.name as adolescent_name, adl.code as adolescent_code,  
    case when adl.gender=1 then 'Male' when adl.gender=2 then 'Female' end as gender,
    adl.age_in_completed_years AS adolescent_age_yrs,
    awc.id as awc_id,
    awc.name as awc_name,
    awc.code as awc_code,
    vlg.id as village_id,
    vlg.name as vlg_name,
    gp.id as gp_id,
    gp.name as gp_name,
    blk.id AS block_id,
    blk.name AS block_name,
    dst.id AS district_id,
    dst.name as dst_name,
    st.id AS state_id,
    st.name as state_name,
    adl.site AS site,
    adl.server_created_on AS created_on 
    FROM application_masters_adolescent adl
     JOIN application_masters_awc awc ON adl.awc_id = awc.id
     JOIN mis_usersitemapping usm on usm.site_id=adl.site 
     JOIN application_masters_cc_awc_ah  cal on adl.awc_id=cal.awc_id and usm.user_id=cal.user_id and cal.status=1
     JOIN auth_user au on cal.user_id=au.id
     JOIN application_masters_village vlg ON awc.village_id = vlg.id
     JOIN application_masters_gramapanchayat gp ON gp.id = vlg.grama_panchayat_id
     JOIN application_masters_block blk ON blk.id = gp.block_id
     JOIN application_masters_district dst ON dst.id = blk.district_id
     JOIN application_masters_state st ON st.id = dst.state_id
  WHERE adl.status = 1 and site={current_site} {dst_id} {blk_id} {pyt_id} {vlg_id} {awc_id} {cc_id} {age_range}'''
    adolescent_list=SqlHeader(query)

    if export == 'adolescent_list':
        export_flag = 'adolescent_list' if request.GET.get('export') and request.GET.get('export').lower() == 'adolescent_list' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Adolescent list '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'User ID',
                'User Name',
                'Adolescent ID',
                'Adolescent Name',
                'Adolescent code',
                'Age',
                'Gender',
                'AWC ID',
                'AWC Name',
                'AWC code',
                'Village ID',
                'Village Name',
                'Gramapanchayat ID',
                'Gramapanchayat Name',
                'Block ID',
                'Block Name',
                'District ID',
                'District Name',
                'State ID',
                'State Name',
                ])
            for data in adolescent_list:
                writer.writerow([
                    data['user_id'],
                    data['username'],
                    data['adolescent_id'],
                    data['adolescent_name'],
                    data['adolescent_code'],
                    data['adolescent_age_yrs'],
                    data['gender'],
                    data['awc_id'],
                    data['awc_name'],
                    data['awc_code'],
                    data['village_id'],
                    data['vlg_name'],
                    data['gp_id'],
                    data['gp_name'],
                    data['block_id'],
                    data['block_name'],
                    data['district_id'],
                    data['dst_name'],
                    data['state_id'],
                    data['state_name'],
                    ])
            return response
    return render(request, 'reports/adolescent_report.html', locals())


@ login_required(login_url='/login/')
def report_list(request):
    heading="Reports List"
    from datetime import datetime
    from dateutil.relativedelta import relativedelta

    user = get_user(request)
    current_site = request.session.get('site_id')
    section_order = ReportMeta.objects.filter(status=1, site_id=current_site).order_by('display_order')
    user_role = str(user.groups.last())
    filter_values = request.GET.dict()
    start_filter = request.GET.get('start_filter', '')
    end_filter = request.GET.get('end_filter', '')
    reports = request.GET.get('reports', '')
    export=filter_values.get('export')
    # health_sessions = AHSession.objects.filter(status=1, site__id=current_site)#1
    digital_literacy = DLSession.objects.filter(status=1, site__id=current_site)#fossil_only_2
    vocational =  AdolescentVocationalTraining.objects.filter(status=1, site__id=current_site)#2a
    parent_vocational =  ParentVocationalTraining.objects.filter(status=1, site__id=current_site)#2b
    girls_ahwd = GirlsAHWD.objects.filter(status=1, site__id=current_site)#3a
    boys_ahwd = BoysAHWD.objects.filter(status=1, site__id=current_site)#3b
    adolescents_referred =  AdolescentsReferred.objects.filter(status=1, site__id=current_site)#4
    friendly_club = AdolescentFriendlyClub.objects.filter(status=1, site__id=current_site)#5
    balsansad_meeting = BalSansadMeeting.objects.filter(status=1, site__id=current_site)#6
    activities = CommunityEngagementActivities.objects.filter(status=1, site__id=current_site)#7
    champions =  Champions.objects.filter(status=1, site__id=current_site)#8
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter(status=1, site__id=current_site)#9
    stakeholders = Stakeholder.objects.filter(status=1, site__id=current_site)
    vlcpc_meeting = VLCPCMetting.objects.filter(status=1, site__id=current_site)#10
    dcpu_bcpu = DCPU_BCPU.objects.filter(status=1, site__id=current_site)#11
    education_enrichment = EducatinalEnrichmentSupportProvided.objects.filter(status=1, site__id=current_site)#12
    sessions_monitoring = SessionMonitoring.objects.filter(status=1, site__id=current_site)#13
    facility_visits = Events.objects.filter(status=1, site__id=current_site)#14
    participating_meeting = ParticipatingMeeting.objects.filter(status=1, site__id=current_site)#15
    followup_liaision = FollowUP_LiaisionMeeting.objects.filter(status=1, site__id=current_site)#16
    faced_related = FacedRelatedOperation.objects.filter(status=1, site__id=current_site)#17
    sd_year=''
    sd_month=''
    ed_year=''
    ed_month=''
    between_date=""
    if start_filter != '':
        s_date = start_filter+'-01'
        e_date = end_filter+'-01'
        sd_date= datetime.strptime(s_date, "%Y-%m-%d")
        ed_date= datetime.strptime(e_date, "%Y-%m-%d")
        ed_filter = ed_date + relativedelta(months=1)
        between_date = f"""and task.start_date >= '{s_date}' and task.start_date < '{ed_filter}'"""
        # health_sessions = AHSession.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#1
        digital_literacy = DLSession.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#fossil_only_2
        vocational =  AdolescentVocationalTraining.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#2a
        parent_vocational =  ParentVocationalTraining.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#2b
        girls_ahwd = GirlsAHWD.objects.filter(status=1, site__id=current_site,task__start_date__range=[sd_date, ed_date])#3a
        boys_ahwd = BoysAHWD.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#3b
        adolescents_referred =  AdolescentsReferred.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#4
        friendly_club = AdolescentFriendlyClub.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#5
        balsansad_meeting = BalSansadMeeting.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#6
        activities = CommunityEngagementActivities.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#7
        champions =  Champions.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#8
        adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#9
        stakeholders = Stakeholder.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])
        vlcpc_meeting = VLCPCMetting.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#10
        dcpu_bcpu = DCPU_BCPU.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#11
        education_enrichment = EducatinalEnrichmentSupportProvided.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#12
        sessions_monitoring = SessionMonitoring.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#13
        facility_visits = Events.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#14
        participating_meeting = ParticipatingMeeting.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#15
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#16
        faced_related = FacedRelatedOperation.objects.filter(status=1, site__id=current_site, task__start_date__range=[sd_date, ed_date])#17
    sql =f'''select auth_user.username as user, 
    to_char(task.start_date, 'Month YYYY') as c_date, 
    blk.name, gp.name as grama_panchayat_name, 
    vlg.name as vlg_name, ad.name as adolescent_name, 
    ad.code as adolescent_code, fahs.session_name, hs.date_of_session, 
    case when hs.session_day=1 then 'Day-1' when hs.session_day=2 then 'Day-2' when hs.session_day=3 then 'Day-3' end as s_day, 
    hs.facilitator_name, ad.age_in_completed_years, case when ad.gender=1 then 'Male' when ad.gender=2 then 'Female' end as gender, 
    case when hs.designation_data=1 then 'ANM' when hs.designation_data=2 then 'Sahiya' when hs.designation_data=3 then 'Sevika' when hs.designation_data=4 then 'Peer Educator' when hs.designation_data=5 then 'Cluster Coordinator' when hs.designation_data=6 then 'Project Officer'  when hs.designation_data=7 then 'SPO' when hs.designation_data=8 then 'Others' end as designation, 
    hs.server_created_on from mis_ahsession hs 
    inner join mis_task task on hs.task_id=task.id 
    inner join auth_user on task.user_id=auth_user.id 
    inner join application_masters_adolescent ad on hs.adolescent_name_id=ad.id 
    inner join application_masters_awc awc on ad.awc_id=awc.id 
    inner join application_masters_village vlg on awc.village_id=vlg.id 
    inner join application_masters_gramapanchayat gp on vlg.grama_panchayat_id=gp.id 
    inner join application_masters_block blk on gp.block_id=blk.id 
    inner join application_masters_fossilahsession fahs on fossil_ah_session_id=fahs.id 
    where 1=1 and hs.status=1 and hs.site_id={current_site} {between_date}'''
    cursor = connection.cursor()
    cursor.execute(sql)
    health_sessions = cursor.fetchall()


    if export == 'health_sessions':
        export_flag = 'health_sessions' if request.GET.get('export') and request.GET.get('export').lower() == 'health_sessions' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Health session'+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Name of the Block',
                'Name of the Panchayat',
                'Name of the Village',
                'Name of Adolescent',
                'Name of Adolescent Code',
                'Session name',
                'Date of session',
                'Session Day',
                'Name of the main Facilitator',
                'Age',
                'Gender',
                'Designation',
                'Created On',
                ])
            for data in health_sessions:
                writer.writerow([
                    data[0],
                    data[1],
                    data[2],
                    data[3],
                    data[4],
                    data[5],
                    data[6],
                    data[7],
                    data[8],
                    data[9],
                    data[10],
                    data[11],
                    data[12],
                    data[13],
                    data[14],
                    ])
            return response
    elif export == 'digital_literacy':
        export_flag = 'digital_literacy' if request.GET.get('export') and request.GET.get('export').lower() == 'digital_literacy' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Digital Literacy '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Name of Panchayat',
                'Name of Village',
                'Name of AWC',
                'Name of Adolescent',
                'Session name',
                'Date of session',
                'Session Day',
                'Name of the Facilitator',
                'Gender',
                'Designation',
                'Created On',
                ])
            for data in digital_literacy:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.adolescent_name.awc.village.grama_panchayat,
                    data.adolescent_name.awc.village,
                    data.adolescent_name.awc,
                    data.adolescent_name,
                    data.fossil_dl_session_config,
                    data.date_of_session,
                    data.get_session_day_display(),
                    data.facilitator_name,
                    data.get_gender_display(),
                    data.get_designation_data_display(),
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'vocational':
        export_flag = 'vocational' if request.GET.get('export') and request.GET.get( 'export').lower() == 'vocational' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Vocational Training'+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Name of Panchayat',
                'Name of Village',
                'Name of the adolescent boys',
                'Date of registration',
                'Parent/guardian name',
                'Training subject',
                'Training providing by',
                'Duration in days',
                'Training completed',
                'Placement offered',
                'Placement accepted',
                'Type of employment',
                'Created On',
                ])
            for data in vocational:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.adolescent_name.awc.village.grama_panchayat,
                    data.adolescent_name.awc.village,
                    data.adolescent_name,
                    data.date_of_registration,
                    data.parent_guardian_name,
                    data.training_subject.training_subject,
                    data.get_training_providing_by_display(),
                    data.duration_days,
                    data.get_training_complated_display(),
                    data.get_placement_offered_display(),
                    data.get_placement_accepted_display(),
                    data.get_type_of_employment_display(),
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'parent_vocational':
        export_flag = 'parent_vocational' if request.GET.get('export') and request.GET.get( 'export').lower() == 'parent_vocational' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Parent Vocational Training'+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Name of the parents linked',
                'Date of registration',
                'Parent/guardian name',
                'Training subject',
                'Training providing by',
                'Duration in days',
                'Training completed',
                'Placement offered',
                'Placement accepted',
                'Type of employment',
                'Created On',
                ])
            for data in parent_vocational:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.adolescent_name,
                    data.date_of_registration,
                    data.parent_name,
                    data.training_subject.training_subject,
                    data.get_training_providing_by_display(),
                    data.duration_days,
                    data.get_training_complated_display(),
                    data.get_placement_offered_display(),
                    data.get_placement_accepted_display(),
                    data.get_type_of_employment_display(),
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'girls_ahwd':
        export_flag = 'girls_ahwd' if request.GET.get('export') and request.GET.get( 'export').lower() == 'girls_ahwd' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Adolescent girls(AHWD) '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Date of AHWD',
                'Name of Panchayat',
                'Name of Village',
                'Place of the AHWD',
                'Name of the AWC, HWC, School',
                'Number of adolescent girls participated 10-14 year',
                'Number of adolescent girls participated 15-19 year',
                'Number of adolescent who received services BMI 10-14 year',
                'Number of adolescent who received services BMI 15-19 year',
                'Number of adolescent who received services TT shot 10-14 year',
                'Number of adolescent who received services TT shot 15-19 year',
                'Number of adolescent who received services HB test 10-14 year',
                'Number of adolescent who received services HB test 15-19 year',
                'Number of adolescent who received services Counselling 10-14 year',
                'Number of adolescent who received services Counselling 15-19 year',
                'Number of adolescent who received services Referral 10-14 year',
                'Number of adolescent who received services Referral 15-19 year',
                'Created On',
                ])
            for data in girls_ahwd:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.date_of_ahwd,
                    data.content_object.village.grama_panchayat if data.content_object else "Not applicable",
                    data.content_object.village if data.content_object else "Not applicable",
                    data.get_place_of_ahwd_display(),
                    data.content_object or data.hwc_name,
                    data.participated_10_14_years,
                    data.participated_15_19_years,
                    data.bmi_10_14_years,
                    data.bmi_15_19_years,
                    data.tt_10_14_years,
                    data.tt_15_19_years,
                    data.hb_10_14_years,
                    data.hb_15_19_years,
                    data.counselling_10_14_years,
                    data.counselling_15_19_years,
                    data.referral_10_14_years,
                    data.referral_15_19_years,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'boys_ahwd':
        export_flag = 'boys_ahwd' if request.GET.get('export') and request.GET.get( 'export').lower() == 'boys_ahwd' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Adolescent boys(AHWD) '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Date of AHWD',
                'Name of Panchayat',
                'Name of Village',
                'Place of the AHWD',
                'Name of the AWC, HWC, School',
                'Number of adolescent boys participated 10-14 year',
                'Number of adolescent boys participated 15-19 year',
                'Number of adolescent who received services BMI 10-14 year',
                'Number of adolescent who received services BMI 15-19 year',
                'Number of adolescent who received services HB test 10-14 year',
                'Number of adolescent who received services HB test 15-19 year',
                'Number of adolescent who received services Counselling 10-14 year',
                'Number of adolescent who received services Counselling 15-19 year',
                'Number of adolescent who received services Referral 10-14 year',
                'Number of adolescent who received services Referral 15-19 year',
                'Created On',
                ])
            for data in boys_ahwd:  
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.date_of_ahwd,
                    data.content_object.village.grama_panchayat if data.content_object else "Not applicable",
                    data.content_object.village if data.content_object else "Not applicable",
                    data.get_place_of_ahwd_display(),
                    data.content_object or data.hwc_name,
                    data.participated_10_14_years,
                    data.participated_15_19_years,
                    data.bmi_10_14_years,
                    data.bmi_15_19_years,
                    data.hb_10_14_years,
                    data.hb_15_19_years,
                    data.counselling_10_14_years,
                    data.counselling_15_19_years,
                    data.referral_10_14_years,
                    data.referral_15_19_years,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'adolescents_referred':
        export_flag = 'adolescents_referred' if request.GET.get('export') and request.GET.get('export').lower() == 'adolescents_referred' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Adolescent Referred '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Name of Panchayat',
                'Name of Village',
                'Name of the AWC',
                'Number of adolescent girls referred 10-14 year',
                'Number of adolescent girls referred 15-19 year',
                'Number of adolescent boys referred 10-14 year',
                'Number of adolescent boys referred 15-19 year',
                'Number of adolescent girls HWC Referred',
                'Number of adolescent girls HWC Visited',
                'Number of adolescent girls AFHC Referred',
                'Number of adolescent girls AFHC Visited',
                'Number of adolescent girls DH Referred',
                'Number of adolescent girls DH Visited',
                'Number of adolescent boys HWC Referred',
                'Number of adolescent boys HWC Visited',
                'Number of adolescent boys AFHC Referred',
                'Number of adolescent boys AFHC Visited',
                'Number of adolescent boys DH Referred',
                'Number of adolescent boys DH Visited',
                'Created On',
                ])
            for data in adolescents_referred:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.awc_name.village.grama_panchayat,
                    data.awc_name.village,
                    data.awc_name,
                    data.girls_referred_10_14_year,
                    data.girls_referred_15_19_year,
                    data.boys_referred_10_14_year,
                    data.girls_referred_15_19_year,
                    data.girls_hwc_referred,
                    data.girls_hwc_visited,
                    data.girls_afhc_referred,
                    data.girls_afhc_visited,
                    data.girls_dh_referred,
                    data.girls_dh_visited,
                    data.boys_hwc_referred,
                    data.boys_hwc_visited,
                    data.boys_afhc_referred,
                    data.boys_afhc_visited,
                    data.boys_dh_referred,
                    data.boys_dh_visited,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'friendly_club':
        print('ppppppp')
        export_flag = 'friendly_club' if request.GET.get('export') and request.GET.get('export').lower() == 'friendly_club' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Friendly club '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Date',
                'Name of the Panchayat',
                'Name of the HSC',
                'Issue/Subject',
                'Name of the Facilitator',
                'Designation',
                'No of the Sahiya',
                'No of AWW participated',
                'No of PE(girls 10-14 year)',
                'No of PE(girls 15-19 year)',
                'No of PE(boys 10-14 year)',
                'No of PE(boys 15-19 year)',
                'Created On',
                ])
            for data in friendly_club:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.start_date,
                    data.panchayat_name,
                    data.hsc_name,
                    data.subject,
                    data.facilitator,
                    data.get_designation_display(),
                    data.no_of_sahiya,
                    data.no_of_aww,
                    data.pe_girls_10_14_year,
                    data.pe_girls_15_19_year,
                    data.pe_boys_10_14_year,
                    data.pe_boys_15_19_year,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'balsansad_meeting':
        export_flag = 'balsansad_meeting' if request.GET.get('export') and request.GET.get('export').lower() == 'balsansad_meeting' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Balsansad meeting '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Date',
                'Name of Panchayat',
                'Name of School',
                'Number of participants',
                'Issues discussion',
                'Decision taken',
                'Created On',
                ])
            for data in balsansad_meeting:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.start_date,
                    data.school_name.village.grama_panchayat,
                    data.school_name,
                    data.no_of_participants,
                    data.issues_discussion,
                    data.decision_taken,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'activities':
        export_flag = 'activities' if request.GET.get('export') and request.GET.get('export').lower() == 'activities' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Activities '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Date of Activity',
                'Name of Panchayat',
                'Name of Village',
                'Name of the event/activity',
                'Organized by (C3/Govt)',
                'Number of participant adolescent boys 10-14 year',
                'Number of participant adolescent boys 15-19 year',
                'Number of participant adolescent girls 10-14 year',
                'Number of participant adolescent girls 15-19 year',
                'Number of participant champions (15-19 years)',
                'Number of participant adult male from community',
                'Number of participant adult female from community',
                'Number of participant teachers',
                'Number of participant PRI members',
                'Number of participant services providers',
                'Number of participant SMC members',
                'Number of participant others',
                'Created On',
                ])
            for data in activities:
                if data.name_of_event_activity == 1:
                    event_name = data.event_name.name if data.event_name else None
                else:
                    event_name = data.activity_name.name if data.activity_name else None
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.start_date,
                    data.village_name.grama_panchayat,
                    data.village_name,
                    event_name,
                    data.get_organized_by_display(),
                    data.girls_10_14_year,
                    data.girls_15_19_year,
                    data.boys_10_14_year,
                    data.boys_15_19_year,
                    data.champions_15_19_year,
                    data.adult_male,
                    data.adult_female,
                    data.teachers,
                    data.pri_members,
                    data.services_providers,
                    data.sms_members,
                    data.other,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'champions':
        export_flag = 'champions' if request.GET.get('export') and request.GET.get('export').lower() == 'champions' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Champions '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Date of Visit',
                'Name of Panchayat',
                'Name of Village',
                'Name of AWC',
                'No of Champions (Girls 10-14 year)',
                'No of Champions (Girls 15-19 year)',
                'No of Champions (Boys 10-14 year)',
                'No of Champions (Boys 15-19 year)',
                'Name of institutions visited First',
                'Name of institutions visited Second',
                'Name of institutions visited Third',
                'Name of institutions visited Fourth',
                'Created On',
                ])
            for data in champions:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.date_of_visit,
                    data.awc_name.village.grama_panchayat,
                    data.awc_name.village,
                    data.awc_name,
                    data.girls_10_14_year,
                    data.girls_15_19_year,
                    data.boys_10_14_year,
                    data.boys_15_19_year,
                    data.get_first_inst_visited_display(),
                    data.get_second_inst_visited_display(),
                    data.get_third_inst_visited_display(),
                    data.get_fourth_inst_visited_display(),
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    if export == 'adolescent_reenrolled':
        export_flag = 'adolescent_reenrolled' if request.GET.get('export') and request.GET.get('export').lower() == 'adolescent_reenrolled' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Adolescent reenrolled '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Name of Panchayat',
                'Name of Village',
                'Name of Adolescent',
                'Gender',
                'Parent/guardian',
                'Name of School',
                'In which Class enrolled',
                'Created On',
                ])
            for data in adolescent_reenrolled:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.adolescent_name.awc.village.grama_panchayat,
                    data.adolescent_name.awc.village,
                    data.adolescent_name,
                    data.get_gender_display(),
                    data.parent_guardian_name,
                    data.school_name,                                    
                    data.get_which_class_enrolled_display(),
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'vlcpc_meeting':
        export_flag = 'vlcpc_meeting' if request.GET.get('export') and request.GET.get('export').lower() == 'vlcpc_meeting' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="VLCPC Meeting '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Name of Block',
                'Name of Panchayat',
                'Name of Village',
                'Name of AWC',
                'Date of mettings',
                'Issues discussed',
                'Decision taken',
                'No. of Participants Planned',
                'No. of Participants Attended',
                'Created On',
                ])
            for data in vlcpc_meeting:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.awc_name.village.grama_panchayat.block,
                    data.awc_name.village.grama_panchayat,
                    data.awc_name.village,
                    data.awc_name,
                    data.date_of_meeting,
                    data.issues_discussed,
                    data.decision_taken,
                    data.no_of_participants_planned,
                    data.no_of_participants_attended,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'dcpu_bcpu':
        export_flag = 'dcpu_bcpu' if request.GET.get('export') and request.GET.get('export').lower() == 'dcpu_bcpu' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="DCPU/BCPU Engagement '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Name of the Block/district',
                'Name of the Institutions',
                'Date of Visit',
                'Name of lead of the meeting',
                'Designation',
                'Issues discussed',
                'Number of participants adolescent boys 10-14 year',
                'Number of participants adolescent boys 15-19 year',
                'Number of participants adolescent girls 10-14 year',
                'Number of participants adolescent girls 15-19 year',
                'Number of participants champions (15-19 years)',
                'Number of participants adult male from community',
                'Number of participants adult female from community',
                'Number of participants teachers',
                'Number of participants PRI members',
                'Number of participants services providers',
                'Number of participants SMS members',
                'Number of participants other',
                'Created On',
                ])
            for data in dcpu_bcpu:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.block_name,
                    data.name_of_institution,
                    data.date_of_visit,
                    data.name_of_lead,
                    data.designation,
                    data.issues_discussed,
                    data.girls_10_14_year,
                    data.girls_15_19_year,
                    data.boys_10_14_year,
                    data.boys_15_19_year,
                    data.champions_15_19_year,
                    data.adult_male,
                    data.adult_female,
                    data.teachers,
                    data.pri_members,
                    data.services_providers, 
                    data.sms_members,
                    data.other,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'education_enrichment':
        export_flag = 'education_enrichment' if request.GET.get('export') and request.GET.get('export').lower() == 'education_enrichment' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Education Enrichment '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Name of Block',
                'Name of Panchayat',
                'Name of Village',
                'Name of AWC',
                'Name of the adolescent girls',
                'Parent/guardian',
                'Enrolment date',
                'Class (VIII, IX & X)',
                'Duration of coaching support',
                'Created On',
                ])
            for data in education_enrichment:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.adolescent_name.awc.village.grama_panchayat.block,
                    data.adolescent_name.awc.village.grama_panchayat,
                    data.adolescent_name.awc.village,
                    data.adolescent_name.awc.name,
                    data.adolescent_name,
                    data.parent_guardian_name,
                    data.enrolment_date,
                    data.get_standard_display(),
                    data.duration_of_coaching_support,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'stakeholders':
        export_flag = 'stakeholders' if request.GET.get('export') and request.GET.get('export').lower() == 'stakeholders' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Stakeholders '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',  
                'Education department master trainers male',
                'Education department master trainers female',
                'Education department master trainers total',
                'Education department nodal teachers male',
                'Education department nodal teachers female',
                'Education department nodal teachers total',
                'Education department principals male',
                'Education department principals female',
                'Education department principals total',
                'Education department district level officials male',
                'Education department district level officials female',
                'Education department district level officials total',
                'Education department peer educator male',
                'Education department peer educator female',
                'Education department peer educator total',
                'Education department state level officials male',
                'Education department state level officials female',
                'Education department state level officials total',
                'ICDS department AWWs male',
                'ICDS department AWWs female',
                'ICDS department AWWs total',
                'ICDS department supervisors male',
                'ICDS department supervisors female',
                'ICDS department supervisors total',
                'ICDS department peer educator male',
                'ICDS department peer educator female',
                'ICDS department peer educator total',
                'ICDS department child developement project officers male',
                'ICDS department child developement project officers female',
                'ICDS department child developement project officers total',
                'ICDS department district level officials male',
                'ICDS department district level officials female',
                'ICDS department district level officials total',
                'ICDS department state level officials male',
                'ICDS department state level officials female',
                'ICDS department state level officials total',
                'Health department ASHAs male',
                'Health department ASHAs female',
                'Health department ASHAs total',
                'Health department ANMs male',
                'Health department ANMs female',
                'Health department ANMs total',
                'Health department BPM/BHM/PHEOs male',
                'Health department BPM/BHM/PHEOs female',
                'Health department BPM/BHM/PHEOs total',
                'Health department medical officers male',
                'Health department medical officers female',
                'Health department medical officers total',
                'Health department district level officials male',
                'Health department district level officials female',
                'Health department district level officials total',
                'Health department state level officials male',
                'Health department state level officials female',
                'Health department state level officials total',
                'Health department RKS male',
                'Health department RKS female',
                'Health department RKS total',
                'Health department peer educator male',
                'Health department peer educator female',
                'Health department peer educator total',
                'Panchayat raj department ward members male',
                'Panchayat raj department ward members female',
                'Panchayat raj department ward members total',
                'Panchayat raj department Up-mukhiya/Up-pramukh male',
                'Panchayat raj department Up-mukhiya/Up-pramukh female',
                'Panchayat raj department Up-mukhiya/Up-pramukh total',
                'Panchayat raj department mukhiya Pramukh male',
                'Panchayat raj department mukhiya Pramukh female',
                'Panchayat raj department mukhiya Pramukh total',
                'Panchayat raj department samiti member male',
                'Panchayat raj department samiti member female',
                'Panchayat raj department samiti member total',
                'Panchayat raj department zila parishad member male',
                'Panchayat raj department zila parishad member female',
                'Panchayat raj department zila parishad member total',
                'Panchayat raj department Vc-Zila parishad male',
                'Panchayat raj department Vc-Zila parishad female',
                'Panchayat raj department Vc-Zila parishad total',
                'Panchayat raj department chairman zila parishad male',
                'Panchayat raj department chairman zila parishad female',
                'Panchayat raj department chairman zila parishad total',
                'Panchayat raj department block level officials male',
                'Panchayat raj department block level officials female',
                'Panchayat raj department block level officials total',
                'Panchayat raj department district level officials male',
                'Panchayat raj department district level officials female',
                'Panchayat raj department district level officials total',
                'Panchayat raj department state level officials male',
                'Panchayat raj department state level officials female',
                'Panchayat raj department state level officials total',
                'Media interns male',
                'Media interns female',
                'Media interns total',
                'Media journalists male',
                'Media journalists female',
                'Media journalists total',
                'Media editors male',
                'Media editors female',
                'Media editors total',
                'Others block cluster field corrdinators male',
                'Others block cluster field corrdinators female',
                'Others block cluster field corrdinators total',
                'Others ngo staff corrdinators male',
                'Others ngo staff corrdinators female',
                'Others ngo staff corrdinators total',
                'Others male',
                'Others female',
                'Others total',
                'Total male',
                'Total female',
                'Total',
                'Created On',
                ])
            for data in stakeholders:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.master_trainers_male,
                    data.master_trainers_female,
                    data.master_trainers_total,
                    data.nodal_teachers_male,
                    data.nodal_teachers_female,
                    data.nodal_teachers_total,
                    data.principals_male,
                    data.principals_female,
                    data.principals_total,
                    data.district_level_officials_male,
                    data.district_level_officials_female,
                    data.district_level_officials_total,
                    data.peer_educator_male,
                    data.peer_educator_female,
                    data.peer_educator_total,
                    data.state_level_officials_male,
                    data.state_level_officials_female,
                    data.state_level_officials_total,
                    data.icds_awws_male,
                    data.icds_awws_female,
                    data.icds_awws_total,
                    data.icds_supervisors_male,
                    data.icds_supervisors_female,
                    data.icds_supervisors_total,
                    data.icds_peer_educator_male,
                    data.icds_peer_educator_female,
                    data.icds_peer_educator_total,
                    data.icds_child_developement_project_officers_male,
                    data.icds_child_developement_project_officers_female,
                    data.icds_child_developement_project_officers_total,
                    data.icds_district_level_officials_male,
                    data.icds_district_level_officials_female,
                    data.icds_district_level_officials_total,
                    data.icds_state_level_officials_male,
                    data.icds_state_level_officials_female,
                    data.icds_state_level_officials_total,
                    data.health_ashas_male,
                    data.health_ashas_female,
                    data.health_ashas_total,
                    data.health_anms_male,
                    data.health_anms_female,
                    data.health_anms_total,
                    data.health_bpm_bhm_pheos_male,
                    data.health_bpm_bhm_pheos_female,
                    data.health_bpm_bhm_pheos_total,
                    data.health_medical_officers_male,
                    data.health_medical_officers_female,
                    data.health_medical_officers_total,
                    data.health_district_level_officials_male,
                    data.health_district_level_officials_female,
                    data.health_district_level_officials_total,
                    data.health_state_level_officials_male,
                    data.health_state_level_officials_female,
                    data.health_state_level_officials_total,
                    data.health_rsk_male,
                    data.health_rsk_female,
                    data.health_rsk_total,
                    data.health_peer_educator_male,
                    data.health_peer_educator_female,
                    data.health_peer_educator_total,
                    data.panchayat_ward_members_male,
                    data.panchayat_ward_members_female,
                    data.panchayat_ward_members_total,
                    data.panchayat_up_mukhiya_up_Pramukh_male,
                    data.panchayat_up_mukhiya_up_Pramukh_female,
                    data.panchayat_up_mukhiya_up_Pramukh_total,
                    data.panchayat_mukhiya_Pramukh_male,
                    data.panchayat_mukhiya_Pramukh_female,
                    data.panchayat_mukhiya_Pramukh_total,
                    data.panchayat_samiti_member_male,
                    data.panchayat_samiti_member_female,
                    data.panchayat_samiti_member_total,
                    data.panchayat_zila_parishad_member_male,
                    data.panchayat_zila_parishad_member_female,
                    data.panchayat_zila_parishad_member_total,
                    data.panchayat_vc_zila_parishad_male,
                    data.panchayat_vc_zila_parishad_female,
                    data.panchayat_vc_zila_parishad_total,
                    data.panchayat_chairman_zila_parishad_male,
                    data.panchayat_chairman_zila_parishad_female,
                    data.panchayat_chairman_zila_parishad_total,
                    data.panchayat_block_level_officials_male,
                    data.panchayat_block_level_officials_female,
                    data.panchayat_block_level_officials_total,
                    data.panchayat_district_level_officials_male,
                    data.panchayat_district_level_officials_female,
                    data.panchayat_district_level_officials_total,
                    data.panchayat_state_level_officials_male,
                    data.panchayat_state_level_officials_female,
                    data.panchayat_state_level_officials_total,
                    data.media_interns_male,
                    data.media_interns_female,
                    data.media_interns_total,
                    data.media_journalists_male,
                    data.media_journalists_female,
                    data.media_journalists_total,
                    data.media_editors_male,
                    data.media_editors_female,
                    data.media_editors_total,
                    data.others_block_cluster_field_corrdinators_male,
                    data.others_block_cluster_field_corrdinators_female,
                    data.others_block_cluster_field_corrdinators_total,
                    data.others_ngo_staff_corrdinators_male,
                    data.others_ngo_staff_corrdinators_female,
                    data.others_ngo_staff_corrdinators_total,
                    data.others_male,
                    data.others_female,
                    data.others_total,
                    data.total_male,
                    data.total_female,
                    data.total,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'sessions_monitoring':
        export_flag = 'sessions_monitoring' if request.GET.get('export') and request.GET.get('export').lower() == 'sessions_monitoring' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Sessions monitoring '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',  
                'Date',
                'Name of Block',
                'Name of panchayat',
                'Name of Village/School/AWC visited',
                'Sessions attended',
                'Observation',
                'Recommendation',
                'Created On',
                ])
            for data in sessions_monitoring:
                if data.name_of_visited == 1:
                    grama_panchayat = data.content_object.grama_panchayat if data.content_object else "Not applicable"
                    block = data.content_object.grama_panchayat.block if data.content_object else "Not applicable"
                else:
                    grama_panchayat = data.content_object.village.grama_panchayat if data.content_object else "Not applicable"
                    block = data.content_object.village.grama_panchayat.block if data.content_object else "Not applicable"
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.date,
                    block,
                    grama_panchayat,
                    data.content_object or data.name_of_place_visited,
                    data.session_attended,
                    data.observation,
                    data.recommendation,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'facility_visits':
        export_flag = 'facility_visits' if request.GET.get('export') and request.GET.get('export').lower() == 'facility_visits' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Sessions monitoring '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Date',
                'Name of Block',
                'Name of Panchayat',
                'Place visited',
                'Purpose of visit',
                'Observation',
                'Recommendation',
                'Created On',
                ])
            for data in facility_visits:
                if data.name_of_visited == 1:
                    grama_panchayat = data.content_object.grama_panchayat if data.content_object else "Not applicable"
                    block = data.content_object.grama_panchayat.block if data.content_object else "Not applicable"
                else:
                    grama_panchayat = data.content_object.village.grama_panchayat if data.content_object else "Not applicable"
                    block = data.content_object.village.grama_panchayat.block if data.content_object else "Not applicable"
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.date,
                    block,
                    grama_panchayat,
                    data.content_object or data.name_of_place_visited,
                    data.purpose_visited,
                    data.observation,
                    data.recommendation, 
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'participating_meeting':
        export_flag = 'participating_meeting' if request.GET.get('export') and request.GET.get('export').lower() == 'participating_meeting' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Participating Meeting '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Date',
                'District/Block Level',
                'Type of meeting',
                'With which department?',
                'Point of discussion',
                'Number of adolescent girls district level officials',
                'Number of adolescent girls block level',
                'Number of adolescent girls cluster level',
                'Number of adolescent girls PRI',
                'Number of adolescent girls Others',
                'Created On',
                ])
            for data in participating_meeting:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.date,
                    data.get_district_block_level_display(),
                    data.get_type_of_meeting_display(),
                    data.get_department_display(),
                    data.point_of_discussion,
                    data.districit_level_officials,
                    data.block_level,
                    data.cluster_level,
                    data.no_of_pri,
                    data.no_of_others,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'followup_liaision':
        export_flag = 'followup_liaision' if request.GET.get('export') and request.GET.get('export').lower() == 'followup_liaision' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Followup Liaision '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Date',
                'District/Block Level',
                'Meeting with (designation)',
                'Department',
                'Points of discussion',
                'Outcome',
                'Decision taken',
                'Remarks',
                'Created On',
                ])
            for data in followup_liaision:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.date,
                    data.get_district_block_level_display(),
                    data.meeting_name.name,
                    data.get_departments_display(),
                    data.point_of_discussion,
                    data.outcome,                                    
                    data.decision_taken,  
                    data.remarks,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    elif export == 'faced_related':
        export_flag = 'faced_related' if request.GET.get('export') and request.GET.get('export').lower() == 'faced_related' else False
        if export_flag:
            response = HttpResponse(content_type='text/csv',)
            response['Content-Disposition'] = 'attachment; filename="Faced Related '+ str(localtime(timezone.now()).strftime("%Y/%m/%d %I:%M %p")) +'.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Name of User',
                'Month & year',
                'Challenges (LIST)',
                'Proposed solution',
                'Created On',
                ])
            for data in faced_related:
                writer.writerow([
                    data.task.user,
                    data.task.start_date.strftime("%B %Y"),
                    data.challenges,
                    data.proposed_solution,
                    data.server_created_on.strftime("%Y/%m/%d %I:%M %p"),
                    ])
            return response
    return render(request, 'dashboard/report_list.html', locals())


@ login_required(login_url='/login/')
def fossil_cc_monthly_report(request, task_id):
    current_site = request.session.get('site_id')
    task_obj = Task.objects.get(status=1, id=task_id)
    awc_id = CC_AWC_AH.objects.filter(status=1, user=task_obj.user).values_list('awc__id')
    user = get_user(request)
    user_role = str(user.groups.last())
    awc_objs = AWC.objects.filter(status=1, id__in = awc_id)
    village_id = awc_objs.values_list('village__id', flat=True )
    no_of_village = Village.objects.filter(id__in=village_id).count()
    block_name = list(set(awc_objs.values_list('village__grama_panchayat__block__name', flat=True )))
    district_name = list(set(awc_objs.values_list('village__grama_panchayat__block__district__name', flat=True)))
    cc_awc_ah = awc_objs.count()
    girls_ahwd = GirlsAHWD.objects.filter(status=1, task__id = task_id)
    boys_ahwd = BoysAHWD.objects.filter(status=1, task__id = task_id)
    health_sessions = AHSession.objects.filter(status=1, task__id = task_id)
    digital_literacy = DLSession.objects.filter(status=1, task__id = task_id)
    vocation =  AdolescentVocationalTraining.objects.filter(status=1,task__id = task_id)
    friendly_club = AdolescentFriendlyClub.objects.filter(status=1, task__id = task_id)
    balsansad_meeting = BalSansadMeeting.objects.filter(status=1, task__id = task_id)
    activities = CommunityEngagementActivities.objects.filter(status=1, task__id = task_id)
    adolescents_referred =  AdolescentsReferred.objects.filter(status=1, task__id = task_id)
    champions =  Champions.objects.filter(status=1, task__id = task_id)
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter(status=1, task__id = task_id)
    cc_notes =  CCReportNotes.objects.filter()
    need_revision =  DataEntryRemark.objects.filter(status=1, task__id = task_id).order_by('-server_created_on')
    
    if request.method == 'POST':
        data = request.POST
        successes = data.get('successes')
        challenges_faced = data.get('challenges_faced')
        feasible_solution_to_scale_up = data.get('feasible_solution_to_scale_up')
        task = Task.objects.get(id=task_id)
        if successes or challenges_faced or feasible_solution_to_scale_up:
            cc_notes =  CCReportNotes.objects.create(successes=successes, challenges_faced=challenges_faced, 
            feasible_solution_to_scale_up=feasible_solution_to_scale_up, task=task, site_id = current_site)
            cc_notes.save()
        else:
            return redirect('/fossil/cc/monthly/report/'+str(task_id) + '#fcc-report-notes')
        return redirect('/fossil/cc/monthly/report/'+str(task_id) + '#fcc-report-notes')
    return render(request, 'cc_report/final_fossil.html', locals())

@ login_required(login_url='/login/')
def rnp_cc_monthly_report(request, task_id):
    current_site = request.session.get('site_id')
    task_obj = Task.objects.get(status=1, id=task_id)
    awc_id = CC_AWC_AH.objects.filter(status=1, user=task_obj.user).values_list('awc__id')
    user = get_user(request)
    user_role = str(user.groups.last())
    awc_objs = AWC.objects.filter(status=1, id__in = awc_id)
    block_name = list(set(awc_objs.values_list('village__grama_panchayat__block__name', flat=True)))
    village_id = awc_objs.values_list('village__id', flat=True )
    no_of_village = Village.objects.filter(id__in=village_id).count()
    district_name = list(set(awc_objs.values_list('village__grama_panchayat__block__district__name', flat=True)))
    cc_awc_ah = awc_objs.count()
    vocation =  AdolescentVocationalTraining.objects.filter(status=1, task__id = task_id)
    friendly_club = AdolescentFriendlyClub.objects.filter(status=1, task__id = task_id)
    balsansad_meeting = BalSansadMeeting.objects.filter(status=1, task__id = task_id)
    activities = CommunityEngagementActivities.objects.filter(status=1, task__id = task_id)
    adolescents_referred =  AdolescentsReferred.objects.filter(status=1, task__id = task_id)
    champions =  Champions.objects.filter(status=1, task__id = task_id)
    girls_ahwd = GirlsAHWD.objects.filter(status=1, task__id = task_id)
    boys_ahwd = BoysAHWD.objects.filter(status=1, task__id = task_id)
    health_sessions = AHSession.objects.filter(status=1, task__id = task_id)
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter(status=1, task__id = task_id)
    cc_notes =  CCReportNotes.objects.filter(task__id = task_id)
    need_revision =  DataEntryRemark.objects.filter(status=1, task__id = task_id).order_by('-server_created_on')
    
    if request.method == 'POST':
        data = request.POST
        successes = data.get('successes')
        challenges_faced = data.get('challenges_faced')
        feasible_solution_to_scale_up = data.get('feasible_solution_to_scale_up')
        task = Task.objects.get(id=task_id)
        if successes or feasible_solution_to_scale_up or feasible_solution_to_scale_up:
            cc_notes =  CCReportNotes.objects.create(successes=successes, challenges_faced=challenges_faced, 
            feasible_solution_to_scale_up=feasible_solution_to_scale_up, task=task, site_id = current_site)
            cc_notes.save()
        else:
            return redirect('/rnp/cc/monthly/report/'+str(task_id) + '#rcc-report-notes')

        return redirect('/rnp/cc/monthly/report/'+str(task_id) + '#rcc-report-notes')
        # return redirect('/admin/mis/ccreportnotes/')
    return render(request, 'cc_report/final_rnp.html', locals())

@ login_required(login_url='/login/')
def untrust_cc_monthly_report(request, task_id):
    current_site = request.session.get('site_id')
    task_obj = Task.objects.get(status=1, id=task_id)
    awc_id = CC_AWC_AH.objects.filter(status=1, user=task_obj.user).values_list('awc__id')
    user = get_user(request)
    user_role = str(user.groups.last())
    awc_objs = AWC.objects.filter(status=1, id__in = awc_id)
    village_id = awc_objs.values_list('village__id', flat=True )
    no_of_village = Village.objects.filter(id__in=village_id).count()
    block_name = list(set(awc_objs.values_list('village__grama_panchayat__block__name', flat=True )))
    block_ids = list(set(awc_objs.values_list('village__grama_panchayat__block__id', flat=True )))
    district_name = list(set(awc_objs.values_list('village__grama_panchayat__block__district__name', flat=True)))
    cc_awc_ah = awc_objs.count()
    block_ids = Block.objects.filter(status=1).exclude(id__in=block_ids).values_list('id', flat=True)
#    awc_name__village__grama_panchayat__block__name__in=block_ids 
    dcpu_bcpu = DCPU_BCPU.objects.filter(status=1, task__id = task_id)
    vlcpc_metting = VLCPCMetting.objects.filter(status=1, task__id = task_id)
    girls_ahwd = GirlsAHWD.objects.filter(status=1, task__id = task_id)
    boys_ahwd = BoysAHWD.objects.filter(status=1, task__id = task_id)
    health_sessions = AHSession.objects.filter(status=1, task__id = task_id)
    vocation =  AdolescentVocationalTraining.objects.filter(status=1, task__id = task_id)
    friendly_club = AdolescentFriendlyClub.objects.filter(status=1, task__id = task_id)
    balsansad_meeting = BalSansadMeeting.objects.filter(status=1, task__id = task_id)
    activities = CommunityEngagementActivities.objects.filter(status=1, task__id = task_id)
    education_enrichment = EducatinalEnrichmentSupportProvided.objects.filter(status=1, task__id = task_id)
    parent_vacation =  ParentVocationalTraining.objects.filter(status=1, task__id = task_id)
    adolescents_referred =  AdolescentsReferred.objects.filter(status=1, task__id = task_id)
    champions =  Champions.objects.filter(status=1, task__id = task_id)
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter(status=1, task__id = task_id)
    cc_notes =  CCReportNotes.objects.filter(task__id = task_id)
    need_revision =  DataEntryRemark.objects.filter(status=1, task__id = task_id).order_by('-server_created_on')

    if request.method == 'POST':
        data = request.POST
        successes = data.get('successes')
        challenges_faced = data.get('challenges_faced')
        feasible_solution_to_scale_up = data.get('feasible_solution_to_scale_up')
        task = Task.objects.get(id=task_id)
        # if CCReportNotes.objects.filter(Q(successes__isnull=successes) & Q(challenges_faced__isnull=challenges_faced) & Q(feasible_solution_to_scale_up__isnull=feasible_solution_to_scale_up)).exists():
        if successes or challenges_faced or feasible_solution_to_scale_up:
            cc_notes =  CCReportNotes.objects.create(successes=successes, challenges_faced=challenges_faced, 
            feasible_solution_to_scale_up=feasible_solution_to_scale_up, task=task, site_id = current_site)
            cc_notes.save()
        else:
            return redirect('/untrust/cc/monthly/report/'+str(task_id) + '#ucc-report-notes')

        return redirect('/untrust/cc/monthly/report/'+str(task_id) + '#ucc-report-notes')
        # return redirect('/admin/mis/ccreportnotes/')
    return render(request, 'cc_report/final_un_trust.html', locals())

@ login_required(login_url='/login/')
def fossil_po_monthly_report(request, task_id):
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(get_user(request).groups.last())
    current_site = request.session.get('site_id')
    if (user_role == 'Senior Program Officer'):
        user_report = MisReport.objects.filter(report_to = task_obj.user).values_list('report_person__id', flat=True)
        participating_meeting = ParticipatingMeeting.objects.filter(task__id = task_id)
        faced_related = FacedRelatedOperation.objects.filter(task = task_obj)
        stakeholders_obj = Stakeholder.objects.filter(task = task_obj)
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(task = task_obj)
    else:
        participating_meeting = ParticipatingMeeting.objects.filter(user_name=request.user.id, task__id = task_id)
        faced_related = FacedRelatedOperation.objects.filter(user_name=request.user.id, task = task_obj)
        stakeholders_obj = Stakeholder.objects.filter(user_name=request.user.id, task = task_obj)
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(user_name=request.user.id, task = task_obj)
        user_report = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    
    task  =  Task.objects.filter(user__id__in = user_report, start_date=task_obj.start_date, end_date=task_obj.end_date).values_list('id', flat=True)
    # panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    # village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    # school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    # awc_dl_id = CC_AWC_DL.objects.filter(status=1, user=request.user).values_list('awc__id')

    awc_id = CC_AWC_AH.objects.filter(status=1, user__id__in=user_report).values_list('awc__id', flat=True)
    awc_objs = AWC.objects.filter(id__in=awc_id)
    village_id = awc_objs.values_list('village__id', flat=True )
    no_of_village = Village.objects.filter(id__in=village_id).count()
    block_name = list(set(awc_objs.values_list('village__grama_panchayat__block__name', flat=True )))
    district_name = list(set(awc_objs.values_list('village__grama_panchayat__block__district__name', flat=True)))
    cc_awc_ah = awc_objs.count()

    sessions_monitoring = SessionMonitoring.objects.filter(status=1, task__id = task_id)
    facility_visits = Events.objects.filter(status=1, task__id = task_id)

    health_sessions = ReportSection1.objects.filter(status=1, task__id__in = task)#1
    digital_literacy = ReportSection2.objects.filter(status=1, task__id__in = task)#2
    vocation =  ReportSection3.objects.filter(status=1, task__id__in = task)#3
    girls_ahwd = ReportSection4a.objects.filter(status=1, task__id__in = task)#4a
    boys_ahwd = ReportSection4b.objects.filter(status=1, task__id__in = task)#4b
    adolescents_referred =  ReportSection5.objects.filter(status=1, task__id__in = task)#5
    friendly_club = ReportSection6.objects.filter(status=1, task__id__in = task)#6
    balsansad_meeting = ReportSection7.objects.filter(status=1, task__id__in = task)#7
    activities = ReportSection8.objects.filter(status=1, task__id__in = task)#8
    champions =  ReportSection9.objects.filter(status=1, task__id__in = task)#9
    adolescent_reenrolled =  ReportSection10.objects.filter(status=1, task__id__in = task)#10
    po_notes =  POReportSection17.objects.filter(status=1, task__id = task_id)
    need_revision =  DataEntryRemark.objects.filter(status=1, task__id = task_id).order_by('-server_created_on')

    if request.method == 'POST':
        data = request.POST
        suggestions = data.get('suggestions')
        task = Task.objects.get(id=task_id)
        if suggestions:
            po_notes =  POReportSection17.objects.create(suggestions=suggestions, task=task, site_id = current_site)
            po_notes.save()
        else:
            return redirect('/fossil/po/monthly/report/'+str(task_id) + '#fpos-17')
        return redirect('/fossil/po/monthly/report/'+str(task_id) + '#fpos-17')
    if Stakeholder.objects.filter(task=task_obj).exists():
        error="disabled"
    return render(request, 'po_report/fossil_mis_po.html', locals())


@ login_required(login_url='/login/')
def fossil_spo_monthly_report(request, task_id):
    task_obj = Task.objects.get(status=1, id=task_id)
    
    user = get_user(request)
    current_site = request.session.get('site_id')
    user_role = str(get_user(request).groups.last())

    view_entry_flag = True
    if (user_role == 'Senior Program Officer'):
        user_report = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
        user_report = MisReport.objects.filter(report_to__id__in = user_report).values_list('report_person__id', flat=True)
        sessions_monitoring = SessionMonitoring.objects.filter(status=1, task = task_obj)
        facility_visits = Events.objects.filter(status=1, task = task_obj)
        participating_meeting = ParticipatingMeeting.objects.filter(status=1, task = task_obj)
        faced_related = FacedRelatedOperation.objects.filter(status=1, task = task_obj)
        stakeholders_obj = Stakeholder.objects.filter(status=1, task = task_obj)
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(status=1, task = task_obj)
    else:
        stakeholders_obj = Stakeholder.objects.filter(status=1,  task__id = task_id)
        faced_related = FacedRelatedOperation.objects.filter(status=1,  task__id = task_id)
        participating_meeting = ParticipatingMeeting.objects.filter(status=1,  task__id = task_id)
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(status=1,  task__id = task_id)
        sessions_monitoring = SessionMonitoring.objects.filter(status=1,  task__id = task_id)
        facility_visits = Events.objects.filter(status=1,  task__id = task_id)
        user_report = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
        user_report = MisReport.objects.filter(report_to__id__in = user_report).values_list('report_person__id', flat=True)
        user_report = MisReport.objects.filter(report_to__id__in = user_report).values_list('report_person__id', flat=True)


    
    task  =  Task.objects.filter(user__id__in = user_report, start_date=task_obj.start_date, end_date=task_obj.end_date).values_list('id', flat=True)
    # panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    # village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    # school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    # awc_dl_id = CC_AWC_DL.objects.filter(status=1, user=request.user).values_list('awc__id')

    awc_id = CC_AWC_AH.objects.filter(status=1, user__id__in=user_report).values_list('awc__id', flat=True)
    awc_objs = AWC.objects.filter(id__in=awc_id)
    village_id = awc_objs.values_list('village__id', flat=True )
    no_of_village = Village.objects.filter(id__in=village_id).count()
    block_name = list(set(awc_objs.values_list('village__grama_panchayat__block__name', flat=True )))
    district_name = list(set(awc_objs.values_list('village__grama_panchayat__block__district__name', flat=True)))
    cc_awc_ah = awc_objs.count()

    sessions_monitoring = SessionMonitoring.objects.filter(status=1, task__id = task_id)
    facility_visits = Events.objects.filter(status=1, task__id = task_id)

    health_sessions = ReportSection1.objects.filter(status=1, task__id__in = task)#1
    digital_literacy = ReportSection2.objects.filter(status=1, task__id__in = task)#2
    vocation =  ReportSection3.objects.filter(status=1, task__id__in = task)#3
    girls_ahwd = ReportSection4a.objects.filter(status=1, task__id__in = task)#4a
    boys_ahwd = ReportSection4b.objects.filter(status=1, task__id__in = task)#4b
    adolescents_referred =  ReportSection5.objects.filter(status=1, task__id__in = task)#5
    friendly_club = ReportSection6.objects.filter(status=1, task__id__in = task)#6
    balsansad_meeting = ReportSection7.objects.filter(status=1, task__id__in = task)#7
    activities = ReportSection8.objects.filter(status=1, task__id__in = task)#8
    champions =  ReportSection9.objects.filter(status=1, task__id__in = task)#9
    adolescent_reenrolled =  ReportSection10.objects.filter(status=1, task__id__in = task)#10
    po_notes =  POReportSection17.objects.filter(task__id = task_id)
    need_revision =  DataEntryRemark.objects.filter(status=1, task__id = task_id).order_by('-server_created_on')
    
    if request.method == 'POST':
        data = request.POST
        suggestions = data.get('suggestions')
        task = Task.objects.get(id=task_id)
        if suggestions:
            po_notes =  POReportSection17.objects.create(suggestions=suggestions, task=task, site_id = current_site)
            po_notes.save()
        else:
            return redirect('/fossil/spo/monthly/report/'+str(task_id) + '#fpos-17')

        return redirect('/fossil/spo/monthly/report/'+str(task_id) + '#fpos-17')
    if Stakeholder.objects.filter(task=task_obj).exists():
        error="disabled"
    return render(request, 'po_report/fossil_mis_po.html', locals())


@ login_required(login_url='/login/')
def rnp_po_monthly_report(request, task_id):
    task_obj = Task.objects.get(status=1, id=task_id)
    
    current_site = request.session.get('site_id')
    user = get_user(request)
    user_role = str(user.groups.last())
    if (user_role == 'Senior Program Officer'):
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(task__id = task_id)
        faced_related = FacedRelatedOperation.objects.filter(task__id = task_id)
        participating_meeting = ParticipatingMeeting.objects.filter(task__id = task_id)
        stakeholders_obj = Stakeholder.objects.filter(task__id = task_id)
        user_report = MisReport.objects.filter(report_to = task_obj.user).values_list('report_person__id', flat=True)
        # user_report = MisReport.objects.filter(report_to__id__in = user_report).values_list('report_person__id', flat=True)
    else:
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(user_name=request.user.id, task__id = task_id)
        faced_related = FacedRelatedOperation.objects.filter(user_name=request.user.id, task__id = task_id)
        participating_meeting = ParticipatingMeeting.objects.filter(user_name=request.user.id, task__id = task_id)
        stakeholders_obj = Stakeholder.objects.filter(user_name=request.user.id, task__id = task_id)
        user_report = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
      
    task  =  Task.objects.filter(user__id__in = user_report, start_date=task_obj.start_date, end_date=task_obj.end_date).values_list('id', flat=True)
    awc_id = CC_AWC_AH.objects.filter(status=1, user__id__in=user_report).values_list('awc__id', flat=True)
    awc_objs = AWC.objects.filter(id__in=awc_id)
    village_id = awc_objs.values_list('village__id', flat=True )
    no_of_village = Village.objects.filter(id__in=village_id).count()
    block_name = list(set(awc_objs.values_list('village__grama_panchayat__block__name', flat=True )))
    district_name = list(set(awc_objs.values_list('village__grama_panchayat__block__district__name', flat=True)))
    cc_awc_ah = awc_objs.count()
    
    sessions_monitoring = SessionMonitoring.objects.filter(status=1, task__id = task_id)
    facility_visits = Events.objects.filter(status=1, task__id = task_id)

    health_sessions = ReportSection1.objects.filter(status=1, task__id__in = task)#1
    # digital_literacy = ReportSection2.objects.filter(status=1, task__id__in = task)#2
    vocation =  ReportSection3.objects.filter(status=1, task__id__in = task)#3
    girls_ahwd = ReportSection4a.objects.filter(status=1, task__id__in = task)#4a
    boys_ahwd = ReportSection4b.objects.filter(status=1, task__id__in = task)#4b
    adolescents_referred =  ReportSection5.objects.filter(status=1, task__id__in = task)#5
    friendly_club = ReportSection6.objects.filter(status=1, task__id__in = task)#6
    balsansad_meeting = ReportSection7.objects.filter(status=1, task__id__in = task)#7
    activities = ReportSection8.objects.filter(status=1, task__id__in = task)#8
    champions =  ReportSection9.objects.filter(status=1, task__id__in = task)#9
    adolescent_reenrolled =  ReportSection10.objects.filter(status=1, task__id__in = task)#10

    # girls_ahwd = GirlsAHWD.objects.filter(status=1, task__id = task_id) #4
    # boys_ahwd = BoysAHWD.objects.filter(status=1, task__id = task_id) #5
    # health_sessions = AHSession.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id) #1
    # vocation =  AdolescentVocationalTraining.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id)#3
    # friendly_club = AdolescentFriendlyClub.objects.filter(status=1, panchayat_name__id__in=panchayat_id, task__id = task_id) #7
    # balsansad_meeting = BalSansadMeeting.objects.filter(status=1, school_name__id__in=school_id, task__id = task_id)#8
    # activities =  CommunityEngagementActivities.objects.filter(status=1, village_name__id__in=village_id, task__id = task_id) #6
    # adolescents_referred =  AdolescentsReferred.objects.filter(status=1, awc_name__id__in=awc_id, task__id = task_id)#9
    # champions =  Champions.objects.filter(status=1, awc_name__id__in=awc_id)#10
    # adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id) #11
    
    po_notes =  POReportSection17.objects.filter(task__id = task_id)
    need_revision =  DataEntryRemark.objects.filter(status=1, task__id = task_id).order_by('-server_created_on')
    
    if request.method == 'POST':
        data = request.POST
        suggestions = data.get('suggestions')
        task = Task.objects.get(id=task_id)
        if suggestions:
            po_notes =  POReportSection17.objects.create(suggestions=suggestions, task=task, site_id = current_site)
            po_notes.save()
        else:
            return redirect('/rnp/po/monthly/report/'+str(task_id) + '#rpos-16')

        return redirect('/rnp/po/monthly/report/'+str(task_id) + '#rpos-16')
    if Stakeholder.objects.filter(task=task_id).exists():
        error="disabled"
    return render(request, 'po_report/rnp_mis_po.html', locals())

@ login_required(login_url='/login/')
def rnp_tco_monthly_report(request, task_id):
    task_obj = Task.objects.get(status=1, id=task_id)
    
    current_site = request.session.get('site_id')
    user = get_user(request)
    user_role = str(user.groups.last())
    if (user_role == 'Senior Program Officer'):
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(task__id = task_id)
        faced_related = FacedRelatedOperation.objects.filter(task__id = task_id)
        participating_meeting = ParticipatingMeeting.objects.filter(task__id = task_id)
        stakeholders_obj = Stakeholder.objects.filter(task__id = task_id)
        user_report = MisReport.objects.filter(report_to = task_obj.user).values_list('report_person__id', flat=True)
        # user_report = MisReport.objects.filter(report_to__id__in = user_report).values_list('report_person__id', flat=True)
    else:
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(user_name=request.user.id, task__id = task_id)
        faced_related = FacedRelatedOperation.objects.filter(user_name=request.user.id, task__id = task_id)
        participating_meeting = ParticipatingMeeting.objects.filter(user_name=request.user.id, task__id = task_id)
        stakeholders_obj = Stakeholder.objects.filter(user_name=request.user.id, task__id = task_id)
        user_report = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
   
    # user_report = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    task  =  Task.objects.filter(user__id__in = user_report, start_date=task_obj.start_date, end_date=task_obj.end_date).values_list('id', flat=True)
    # panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    # village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    # school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user__id__in=user_report).values_list('awc__id', flat=True)
    awc_objs = AWC.objects.filter(id__in=awc_id)
    village_id = awc_objs.values_list('village__id', flat=True )
    no_of_village = Village.objects.filter(id__in=village_id).count()

    block_name = list(set(awc_objs.values_list('village__grama_panchayat__block__name', flat=True )))
    district_name = list(set(awc_objs.values_list('village__grama_panchayat__block__district__name', flat=True)))
    cc_awc_ah = awc_objs.count()
    
    sessions_monitoring = SessionMonitoring.objects.filter(status=1, task__id = task_id)
    facility_visits = Events.objects.filter(status=1, task__id = task_id)

    health_sessions = ReportSection1.objects.filter(status=1, task__id__in = task)#1
    # digital_literacy = ReportSection2.objects.filter(status=1, task__id__in = task)#2
    vocation =  ReportSection3.objects.filter(status=1, task__id__in = task)#3
    girls_ahwd = ReportSection4a.objects.filter(status=1, task__id__in = task)#4a
    boys_ahwd = ReportSection4b.objects.filter(status=1, task__id__in = task)#4b
    adolescents_referred =  ReportSection5.objects.filter(status=1, task__id__in = task)#5
    friendly_club = ReportSection6.objects.filter(status=1, task__id__in = task)#6
    balsansad_meeting = ReportSection7.objects.filter(status=1, task__id__in = task)#7
    activities = ReportSection8.objects.filter(status=1, task__id__in = task)#8
    champions =  ReportSection9.objects.filter(status=1, task__id__in = task)#9
    adolescent_reenrolled =  ReportSection10.objects.filter(status=1, task__id__in = task)#10
    po_notes =  POReportSection17.objects.filter(task__id = task_id)
    need_revision =  DataEntryRemark.objects.filter(status=1, task__id = task_id).order_by('-server_created_on')
    
    if request.method == 'POST':
        data = request.POST
        suggestions = data.get('suggestions')
        task = Task.objects.get(id=task_id)
        if suggestions:
            po_notes =  POReportSection17.objects.create(suggestions=suggestions, task=task, site_id = current_site)
            po_notes.save()
        else:
            return redirect('/rnp/tco/monthly/report/'+str(task_id) + '#rpos-16')

        return redirect('/rnp/tco/monthly/report/'+str(task_id) + '#rpos-16')
    if Stakeholder.objects.filter(task=task_id).exists():
        error="disabled"
    return render(request, 'po_report/rnp_mis_po.html', locals())

@ login_required(login_url='/login/')
def rnp_spo_monthly_report(request, task_id):
    task_obj = Task.objects.get(status=1, id=task_id)    
    user = get_user(request)
    user_role = str(get_user(request).groups.last())
    current_site = request.session.get('site_id')

    view_entry_flag = True
    if (user_role == 'Senior Program Officer'):
        user_report = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
        user_report = MisReport.objects.filter(report_to__id__in = user_report).values_list('report_person__id', flat=True)
        
        sessions_monitoring = SessionMonitoring.objects.filter(status=1, task = task_obj)
        facility_visits = Events.objects.filter(status=1, task = task_obj)
        participating_meeting = ParticipatingMeeting.objects.filter(status=1, task = task_obj)
        faced_related = FacedRelatedOperation.objects.filter(status=1, task = task_obj)
        stakeholders_obj = Stakeholder.objects.filter(status=1, task = task_obj)
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(status=1, task = task_obj)
    else:
        stakeholders_obj = Stakeholder.objects.filter(status=1, task = task_obj)
        faced_related = FacedRelatedOperation.objects.filter(status=1, task = task_obj)
        participating_meeting = ParticipatingMeeting.objects.filter(status=1, task = task_obj)
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(status=1, task = task_obj)
        sessions_monitoring = SessionMonitoring.objects.filter(status=1, task = task_obj)
        facility_visits = Events.objects.filter(status=1, task = task_obj)
        user_report = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
        user_report = MisReport.objects.filter(report_to__id__in = user_report).values_list('report_person__id', flat=True)
        user_report = MisReport.objects.filter(report_to__id__in = user_report).values_list('report_person__id', flat=True)
   
    task  =  Task.objects.filter(user__id__in = user_report, start_date=task_obj.start_date, end_date=task_obj.end_date).values_list('id', flat=True)
    awc_id = CC_AWC_AH.objects.filter(status=1, user__id__in=user_report).values_list('awc__id', flat=True)
    awc_objs = AWC.objects.filter(id__in=awc_id)
    village_id = awc_objs.values_list('village__id', flat=True )
    no_of_village = Village.objects.filter(id__in=village_id).count()
    block_name = list(set(awc_objs.values_list('village__grama_panchayat__block__name', flat=True )))
    district_name = list(set(awc_objs.values_list('village__grama_panchayat__block__district__name', flat=True)))
    cc_awc_ah = awc_objs.count()
    
    # sessions_monitoring = SessionMonitoring.objects.filter(status=1, task__id = task_id)
    # facility_visits = Events.objects.filter(status=1, task__id = task_id)

    health_sessions = ReportSection1.objects.filter(status=1, task__id__in = task, )#1
    # digital_literacy = ReportSection2.objects.filter(status=1, task__id__in = task)#2
    vocation =  ReportSection3.objects.filter(status=1, task__id__in = task)#3
    girls_ahwd = ReportSection4a.objects.filter(status=1, task__id__in = task)#4a
    boys_ahwd = ReportSection4b.objects.filter(status=1, task__id__in = task)#4b
    adolescents_referred =  ReportSection5.objects.filter(status=1, task__id__in = task)#5
    friendly_club = ReportSection6.objects.filter(status=1, task__id__in = task)#6
    balsansad_meeting = ReportSection7.objects.filter(status=1, task__id__in = task)#7
    activities = ReportSection8.objects.filter(status=1, task__id__in = task)#8
    champions =  ReportSection9.objects.filter(status=1, task__id__in = task)#9
    adolescent_reenrolled =  ReportSection10.objects.filter(status=1, task__id__in = task)#10
    po_notes =  POReportSection17.objects.filter(task__id = task_id)
    need_revision =  DataEntryRemark.objects.filter(status=1, task__id = task_id).order_by('-server_created_on')
    
    if request.method == 'POST':
        data = request.POST
        suggestions = data.get('suggestions')
        task = Task.objects.get(id=task_id)
        if suggestions:
            po_notes =  POReportSection17.objects.create(suggestions=suggestions, task=task, site_id = current_site)
            po_notes.save()
        else:
            return redirect('/rnp/spo/monthly/report/'+str(task_id) + '#rpos-16')

        return redirect('/rnp/spo/monthly/report/'+str(task_id) + '#rpos-16')
    if Stakeholder.objects.filter(task=task_id).exists():
        error="disabled"
    return render(request, 'po_report/rnp_mis_po.html', locals())

@ login_required(login_url='/login/')
def untrust_po_monthly_report(request, task_id):
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    current_site = request.session.get('site_id')

    user_role = str(user.groups.last())
    if (user_role == 'Senior Program Officer'):
        stakeholders_obj = Stakeholder.objects.filter(task__id = task_id)
        faced_related = FacedRelatedOperation.objects.filter(task__id = task_id)
        participating_meeting = ParticipatingMeeting.objects.filter(task__id = task_id)
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(task__id = task_id)
        user_report = MisReport.objects.filter(report_to = task_obj.user).values_list('report_person__id', flat=True)
        # user_report = MisReport.objects.filter(report_to__id__in = user_report).values_list('report_person__id', flat=True)
    else:
        stakeholders_obj = Stakeholder.objects.filter(user_name=request.user.id, task__id = task_id)
        faced_related = FacedRelatedOperation.objects.filter(user_name=request.user.id, task__id = task_id)
        participating_meeting = ParticipatingMeeting.objects.filter(user_name=request.user.id, task__id = task_id)
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(user_name=request.user.id, task__id = task_id)
        user_report = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    task  =  Task.objects.filter(user__id__in = user_report, start_date=task_obj.start_date, end_date=task_obj.end_date).values_list('id', flat=True)    
    awc_id = CC_AWC_AH.objects.filter(status=1, user__id__in=user_report).values_list('awc__id', flat=True)
    awc_objs = AWC.objects.filter(status=1, id__in=awc_id,)
    village_id = awc_objs.values_list('village__id', flat=True )
    no_of_village = Village.objects.filter(id__in=village_id).count()
    # grama_panchayat = list(set(awc_objs.values_list('village__grama_panchayat__name', flat=True )))
    # print(grama_panchayat)
    # block_ids = awc_objs.values_list('village__grama_panchayat__id', flat=True )
    # block_name = GramaPanchayat.objects.filter(id__in=block_ids).count()
    # print(block_name)
    block_name = list(set(awc_objs.values_list('village__grama_panchayat__block__name', flat=True )))
    district_name = list(set(awc_objs.values_list('village__grama_panchayat__block__district__name', flat=True)))
    cc_awc_ah = awc_objs.count()
    sessions_monitoring = SessionMonitoring.objects.filter(status=1, task__id = task_id)
    
    facility_visits = Events.objects.filter(status=1, task__id = task_id)
    
    education_enrichment = UntrustEducatinalEnrichmentSupportProvided.objects.filter(status=1, task__id__in = task)
    dcpu_bcpu = UntrustDCPU_BCPU.objects.filter(status=1, task__id__in = task)
    vlcpc_metting = UntrustVLCPCMetting.objects.filter(status=1, task__id__in = task)
    health_sessions = ReportSection1.objects.filter(status=1, task__id__in = task)#1
    # digital_literacy = ReportSection2.objects.filter(status=1, task__id__in = task)#2
    vocation =  ReportSection3.objects.filter(status=1, task__id__in = task)#3
    girls_ahwd = ReportSection4a.objects.filter(status=1, task__id__in = task)#4a
    boys_ahwd = ReportSection4b.objects.filter(status=1, task__id__in = task)#4b
    adolescents_referred =  ReportSection5.objects.filter(status=1, task__id__in = task)#5
    friendly_club = ReportSection6.objects.filter(status=1, task__id__in = task)#6
    balsansad_meeting = ReportSection7.objects.filter(status=1, task__id__in = task)#7
    activities = ReportSection8.objects.filter(status=1, task__id__in = task)#8
    champions =  ReportSection9.objects.filter(status=1, task__id__in = task)#9
    adolescent_reenrolled =  ReportSection10.objects.filter(status=1, task__id__in = task)#10
    parent_vacation =  UntrustParentVocationalTraining.objects.filter(status=1, task__id__in = task)
    po_notes =  POReportSection17.objects.filter(task__id = task_id)
    need_revision =  DataEntryRemark.objects.filter(status=1, task__id = task_id).order_by('-server_created_on')
    
    if request.method == 'POST':
        data = request.POST
        suggestions = data.get('suggestions')
        task = Task.objects.get(id=task_id)
        if suggestions:
            po_notes =  POReportSection17.objects.create(suggestions=suggestions, task=task, site_id = current_site)
            po_notes.save()
        else:
            return redirect('/untrust/po/monthly/report/'+str(task_id) + '#upos-19')

        return redirect('/untrust/po/monthly/report/'+str(task_id) + '#upos-19')
    if Stakeholder.objects.filter(task=task_id).exists():
        error="disabled"
    return render(request, 'po_report/un_trust_po.html', locals())

@ login_required(login_url='/login/')
def untrust_spo_monthly_report(request, task_id):
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    current_site = request.session.get('site_id')
    user_role = str(get_user(request).groups.last())
    view_entry_flag = True
    if (user_role == 'Senior Program Officer'):
        user_report = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
        user_report = MisReport.objects.filter(report_to__id__in = user_report).values_list('report_person__id', flat=True)
        sessions_monitoring = SessionMonitoring.objects.filter(status=1, task = task_obj)
        facility_visits = Events.objects.filter(status=1, task = task_obj)
        participating_meeting = ParticipatingMeeting.objects.filter(status=1, task = task_obj)
        faced_related = FacedRelatedOperation.objects.filter(status=1, task = task_obj)
        stakeholders_obj = Stakeholder.objects.filter(status=1, task = task_obj)
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(status=1, task = task_obj)
    else:
        stakeholders_obj = Stakeholder.objects.filter(status=1,  task = task_obj)
        faced_related = FacedRelatedOperation.objects.filter(status=1,  task = task_obj)
        participating_meeting = ParticipatingMeeting.objects.filter(status=1,  task = task_obj)
        followup_liaision = FollowUP_LiaisionMeeting.objects.filter(status=1,  task = task_obj)
        sessions_monitoring = SessionMonitoring.objects.filter(status=1,  task = task_obj)
        facility_visits = Events.objects.filter(status=1,  task = task_obj)
        user_report = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
        user_report = MisReport.objects.filter(report_to__id__in = user_report).values_list('report_person__id', flat=True)
        user_report = MisReport.objects.filter(report_to__id__in = user_report).values_list('report_person__id', flat=True)
    task  =  Task.objects.filter(user__id__in = user_report, start_date=task_obj.start_date, end_date=task_obj.end_date).values_list('id', flat=True)    
    awc_id = CC_AWC_AH.objects.filter(status=1, user__id__in=user_report).values_list('awc__id', flat=True)
    awc_objs = AWC.objects.filter(id__in=awc_id)
    village_id = awc_objs.values_list('village__id', flat=True )
    no_of_village = Village.objects.filter(id__in=village_id).count()
    block_name = list(set(awc_objs.values_list('village__grama_panchayat__block__name', flat=True )))
    district_name = list(set(awc_objs.values_list('village__grama_panchayat__block__district__name', flat=True)))
    cc_awc_ah = awc_objs.count()
    
    
    education_enrichment = UntrustEducatinalEnrichmentSupportProvided.objects.filter(status=1, task__id__in = task)
    dcpu_bcpu = UntrustDCPU_BCPU.objects.filter(status=1, task__id__in = task)
    vlcpc_metting = UntrustVLCPCMetting.objects.filter(status=1, task__id__in = task)
    health_sessions = ReportSection1.objects.filter(status=1, task__id__in = task)#1
    # digital_literacy = ReportSection2.objects.filter(status=1, task__id__in = task)#2
    vocation =  ReportSection3.objects.filter(status=1, task__id__in = task)#3
    girls_ahwd = ReportSection4a.objects.filter(status=1, task__id__in = task)#4a
    boys_ahwd = ReportSection4b.objects.filter(status=1, task__id__in = task)#4b
    adolescents_referred =  ReportSection5.objects.filter(status=1, task__id__in = task)#5
    friendly_club = ReportSection6.objects.filter(status=1, task__id__in = task)#6
    balsansad_meeting = ReportSection7.objects.filter(status=1, task__id__in = task)#7
    activities = ReportSection8.objects.filter(status=1, task__id__in = task)#8
    champions =  ReportSection9.objects.filter(status=1, task__id__in = task)#9
    adolescent_reenrolled =  ReportSection10.objects.filter(status=1, task__id__in = task)#10
    parent_vacation =  UntrustParentVocationalTraining.objects.filter(status=1, task__id__in = task)
    po_notes =  POReportSection17.objects.filter(task__id = task_id)
    need_revision =  DataEntryRemark.objects.filter(status=1, task__id = task_id).order_by('-server_created_on')
    
    if request.method == 'POST':
        data = request.POST
        suggestions = data.get('suggestions')
        task = Task.objects.get(id=task_id)
        if suggestions:
            po_notes =  POReportSection17.objects.create(suggestions=suggestions, task=task, site_id = current_site)
            po_notes.save()
        else:
            return redirect('/untrust/spo/monthly/report/'+str(task_id) + '#upos-19')

        return redirect('/untrust/spo/monthly/report/'+str(task_id) + '#upos-19')
    if Stakeholder.objects.filter(task=task_id).exists():
        error="disabled"
    return render(request, 'po_report/un_trust_po.html', locals())


@ login_required(login_url='/login/')
def add_file(request):
    return render(request, 'dashboard/add_file.html', {})


@ login_required(login_url='/login/')
def monthly_report(request):
    heading = "Monthly Report"
    group = request.user.groups.all()
    # current_site = get_current_site(request)
    # current_site1 = getData(request)
    user_site_obj = UserSiteMapping.objects.get(status=1, user=request.user)
    # user_site_obj.site.objects.get_current()
    task  =  Task.objects.filter(status=1, user = user_site_obj.user,)
    
    user = get_user(request)
    if user.groups.filter(name = 'Program Officer').exists():
        if user_site_obj.site.name in ['fossil', 'c3neev']:
            report_site = '/fossil/po/monthly/report/'

        elif user_site_obj.site.name in ['rnp', 'c3b4b']:
            report_site = '/rnp/po/monthly/report/'
            
        elif user_site_obj.site.name in ['untrust', 'c3manjari']:
            report_site = '/untrust/po/monthly/report/'

    elif (user.groups.filter(name = 'Cluster Coordinator').exists()):
        if user_site_obj.site.name in ['fossil', 'c3neev']:
            report_site = '/fossil/cc/monthly/report/'

        elif user_site_obj.site.name in ['rnp', 'c3b4b']:
            report_site = '/rnp/cc/monthly/report/'
            
        elif user_site_obj.site.name in ['untrust', 'c3manjari']:
            report_site = '/untrust/cc/monthly/report/'
    
    elif (user.groups.filter(name = 'Trainging Coordinator').exists()):
        if user_site_obj.site.name in ['rnp', 'c3b4b']:
            report_site = '/rnp/tco/monthly/report/'
            
    elif (user.groups.filter(name = 'Senior Program Officer').exists()):
        if user_site_obj.site.name in ['fossil', 'c3neev']:
            report_site = '/fossil/spo/monthly/report/'

        elif user_site_obj.site.name in ['rnp', 'c3b4b']:
            report_site = '/rnp/spo/monthly/report/'
            
        elif user_site_obj.site.name in ['untrust', 'c3manjari']:
            report_site = '/untrust/spo/monthly/report/'
   
    return render(request, 'dashboard/task.html', locals())

@ login_required(login_url='/login/')
def logout_view(request):
    logout(request)
    return HttpResponseRedirect('/login/')

#-----------cc-report  fossil---------------

@ login_required(login_url='/login/')
def cc_monthly_report(request):
    heading = "Monthly Report CC Monthly"
    group = request.user.groups.all()
    # current_site = get_current_site(request)
    # current_site1 = getData(request)
    user_site_obj = UserSiteMapping.objects.get(status=1, user=request.user)
    # user_site_obj.site.objects.get_current()
    # task  =  Task.objects.filter(status=1, user = user_site_obj.user,)

    report_person = MisReport.objects.filter(status=1, report_to = request.user).values_list('report_person__id', flat=True)

    task  =  Task.objects.filter(status=1, user__id__in = report_person)
    
    user = get_user(request)
    if user.groups.filter(name = 'Program Officer').exists():
        if user_site_obj.site.name in ['fossil', 'c3neev']:
            report_site = '/fossil/cc/monthly/report/'

        elif user_site_obj.site.name in ['rnp', 'c3b4b']:
            report_site = '/rnp/cc/monthly/report/'
            
        elif user_site_obj.site.name in ['untrust', 'c3manjari']:
            report_site = '/untrust/cc/monthly/report/'
    
    else:
        if user_site_obj.site.name in ['rnp', 'c3b4b']:
            report_site = '/rnp/cc/monthly/report/'
   
    return render(request, 'dashboard/task_list.html', locals())


@ login_required(login_url='/login/')
def tco_monthly_report(request):
    heading = "Monthly Report TC Monthly"
    group = request.user.groups.all()
    user_site_obj = UserSiteMapping.objects.get(status=1, user=request.user)
    user_report = MisReport.objects.filter(status=1, report_to  = request.user).values_list('report_person__id', flat=True)
    user_report_id = User.objects.filter(groups__name='Trainging Coordinator', id__in=user_report).values_list('id', flat=True)
    task  =  Task.objects.filter(status=1, user__id__in = user_report_id)
    user = get_user(request)
   
    if (user.groups.filter(name = 'Senior Program Officer').exists()):
        if user_site_obj.site.name in ['rnp', 'c3b4b']:
            report_site = '/rnp/tco/monthly/report/'
            
    return render(request, 'dashboard/task_list.html', locals())

@ login_required(login_url='/login/')
def po_monthly_report(request):
    heading = "Monthly Report PO Monthly"
    group = request.user.groups.all()
    user_site_obj = UserSiteMapping.objects.get(status=1, user=request.user)
    user_report = MisReport.objects.filter(status=1, report_to  = request.user).values_list('report_person__id', flat=True)
    user_report_id = User.objects.filter(groups__name='Program Officer', id__in=user_report).values_list('id', flat=True)
    task  =  Task.objects.filter(status=1, user__id__in = user_report_id)
    user = get_user(request)
   
    if (user.groups.filter(name = 'Senior Program Officer').exists()):
        if user_site_obj.site.name in ['fossil', 'c3neev']:
            report_site = '/fossil/po/monthly/report/'

        elif user_site_obj.site.name in ['rnp', 'c3b4b']:
            report_site = '/rnp/po/monthly/report/'
            
        elif user_site_obj.site.name in ['untrust', 'c3manjari']:
            report_site = '/untrust/po/monthly/report/'
   
    return render(request, 'dashboard/task_list.html', locals())

@ login_required(login_url='/login/')
def spo_monthly_report(request):
    heading = "Monthly Report SPO Monthly"
    group = request.user.groups.all()
    user_site_obj = UserSiteMapping.objects.get(status=1, user=request.user)
    user_report = MisReport.objects.filter(status=1, report_to  = request.user).values_list('report_person__id', flat=True)
    task  =  Task.objects.filter(status=1, user__id__in = user_report)
    user = get_user(request)
   
    if (user.groups.filter(name = 'Senior Lead').exists()):
        if user_site_obj.site.name in ['fossil', 'c3neev']:
            report_site = '/fossil/spo/monthly/report/'

        elif user_site_obj.site.name in ['rnp', 'c3b4b']:
            report_site = '/rnp/spo/monthly/report/'
            
        elif user_site_obj.site.name in ['untrust', 'c3manjari']:
            report_site = '/untrust/spo/monthly/report/'
   
    return render(request, 'dashboard/task_list.html', locals())

def get_report_block_id(request):
    if request.method == 'GET':
        selected_districts=request.GET.getlist('selected_district[]',[])
        district_to_block_mapping_list = request.session.get('user_district_block_mapping')
        block_lists = []
        [block_lists.extend(district_to_block_mapping_list[i]) for i in selected_districts]
        block_list_ids=[int(key) for block in block_lists for key, value in block.items()]
        result_set = []
        blocks = Block.objects.filter(status=1, id__in=block_list_ids)
        for block in blocks:
            result_set.append(
                {'id': block.id, 'name': block.name,})
        return HttpResponse(json.dumps(result_set))

def get_block_id(request):
    if request.method == 'GET':
        selected_districts=request.GET.getlist('selected_district[]',[])
        result_set = []
        blocks = Block.objects.filter(status=1, district__id__in=selected_districts)
        for block in blocks:
            result_set.append(
                {'id': block.id, 'name': block.name,})
        return HttpResponse(json.dumps(result_set))

def get_grama_panchayat_id(request):
    if request.method == 'GET':
        selected_blocks=request.GET.getlist('selected_block[]',[])
        result_set = []
        grama_panchayats = GramaPanchayat.objects.filter(status=1, block__id__in=selected_blocks).order_by('name').values_list('id', 'name')
        for grama_panchayat in grama_panchayats:
            result_set.append(
                {'id': grama_panchayat[0], 'name': grama_panchayat[1],})
        return HttpResponse(json.dumps(result_set))

def get_village_id(request):
    if request.method == 'GET':
        selected_grama_panchayat=request.GET.getlist('selected_grama_panchayat[]',[])
        result_set = []
        villages = Village.objects.filter(status=1, grama_panchayat__id__in=selected_grama_panchayat).order_by('name').values_list('id', 'name')
        for village in villages:
            result_set.append(
                {'id': village[0], 'name': village[1],})
        return HttpResponse(json.dumps(result_set))

def get_awc_id(request):
    if request.method == 'GET':
        selected_villages=request.GET.getlist('selected_village[]',[])
        result_set = []
        awcs = AWC.objects.filter(status=1, village__id__in=selected_villages).order_by('name').values_list('id', 'name')
        for awc in awcs:
            result_set.append(
                {'id': awc[0], 'name': awc[1],})
        return HttpResponse(json.dumps(result_set))

def get_adolescent(request, awc_id):
    if request.method == 'GET':
        result_set = []
        user_site_obj = UserSiteMapping.objects.get(status=1, user=request.user)
        # It is showing on rnp site at gender male data only.
        if user_site_obj.site.name in ['rnp', 'c3b4b']:
            adolescents = Adolescent.objects.filter(status=1, awc__id=awc_id, site=3).order_by('name')
        elif user_site_obj.site.name in ['untrust', 'c3manjari']:
            adolescents = Adolescent.objects.filter(status=1, awc__id=awc_id, site=4).order_by('name')
        else:
            adolescents = Adolescent.objects.filter(status=1, awc__id=awc_id, site=2).order_by('name')  
        for adolescent in adolescents:
            result_set.append(
                {'id': adolescent.id, 'name': f"{adolescent.name} - {adolescent.code}", })
        return HttpResponse(json.dumps(result_set))

def get_session_name(request, ah_session_id):
    if request.method == 'GET':
        result_set = []
        fossilahsessions = FossilAHSession.objects.filter(status=1, fossil_ah_session_category__id=ah_session_id)
        for fossilahsession in fossilahsessions:
            result_set.append(
                {'id': fossilahsession.id, 'name': fossilahsession.session_name,})
        return HttpResponse(json.dumps(result_set))

@ login_required(login_url='/login/')
def health_sessions_listing_fossil_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 1: Details of transaction of sessions on health & nutrition"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, health_sessions)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/fossil/health_sessions/health_sessions_listing.html', locals())

@ login_required(login_url='/login/')
def add_health_sessions_fossil_cc_report(request, task_id):
    heading = "Section 1: Add of transaction of sessions on health & nutrition"
    current_site = request.session.get('site_id')  
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.filter(task__id = task_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id, site=current_site).order_by('name')
    fossil_ah_session_category_obj =  FossilAHSessionCategory.objects.filter(status=1).exclude(session_category='Engaging Adolescents for Gender Equality Manual')
  
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_selected_id = data.get('awc_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_ah_session_id = data.get('fossil_ah_session')
        fossil_ah_session_selected_id = data.get('fossil_ah_session_category')
        fossil_ah_session = FossilAHSession.objects.get(id=fossil_ah_session_id)
        date_of_session = data.get('date_of_session')
        adolescent_obj =  Adolescent.objects.filter(awc__id=adolescent_selected_id, site=current_site)
        fossil_ah_session_obj =  FossilAHSession.objects.filter(fossil_ah_session_category__id = fossil_ah_session_selected_id)
        session_day = data.get('session_day')
        
        age = data.get('age')
        gender = (data.get('gender'))
        facilitator_name = data.get('facilitator_name')
        designations = data.get('designations')
        task = Task.objects.get(id=task_id)
        if AHSession.objects.filter(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
                                    date_of_session=date_of_session,  status=1).exists():
            exist_error = "Please try again this data already exists!!!"
            return render(request,'cc_report/fossil/health_sessions/add_health_sessions.html', locals())
        else:
            health_sessions = AHSession.objects.create(adolescent_name=adolescent_name, age=age or None, gender=gender or None, fossil_ah_session=fossil_ah_session,
            date_of_session=date_of_session, session_day=session_day, task=task, site_id = current_site, designation_data = designations, facilitator_name = facilitator_name)
            health_sessions.save()
        return redirect('/cc-report/fossil/health-sessions-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/health_sessions/add_health_sessions.html', locals())


@ login_required(login_url='/login/')
def edit_health_sessions_fossil_cc_report(request, ahsession_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 1: Edit of transaction of sessions on health & nutrition"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.get(id=ahsession_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id=health_sessions.adolescent_name.awc.id, site=current_site)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    fossil_ah_session_obj =  FossilAHSession.objects.filter(status=1, fossil_ah_session_category__id=health_sessions.fossil_ah_session.fossil_ah_session_category.id)
    fossil_ah_session_category_obj =  FossilAHSessionCategory.objects.filter(status=1,).exclude(session_category='Engaging Adolescents for Gender Equality Manual')
    
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_ah_session_id = data.get('fossil_ah_session')
        fossil_ah_session = FossilAHSession.objects.get(id=fossil_ah_session_id)
        age = data.get('age')
        gender_data = data.get('gender')
        gender = str(gender_data)
        fossil_ah_session_category = int(data.get('fossil_ah_session_category'))
        facilitator_name = data.get('facilitator_name')
        designations = str(data.get('designations'))
        date_of_session = data.get('date_of_session')
        session_day = data.get('session_day')
        if AHSession.objects.filter(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
                                    date_of_session=date_of_session,  status=1).exclude(id=ahsession_id).exists():
            exist_error = "Please try again this data already exists!!!"
            return render(request,'cc_report/fossil/health_sessions/edit_health_sessions.html', locals())
        else:
            health_sessions.adolescent_name_id = adolescent_name
            health_sessions.fossil_ah_session_id = fossil_ah_session
            health_sessions.date_of_session = date_of_session
            health_sessions.session_day = session_day
            health_sessions.gender = gender or None
            health_sessions.age = age or None
            health_sessions.designation_data = designations
            health_sessions.facilitator_name = facilitator_name
            health_sessions.site_id =  current_site
            health_sessions.save()
        return redirect('/cc-report/fossil/health-sessions-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/health_sessions/edit_health_sessions.html', locals())




@ login_required(login_url='/login/')
def digital_literacy_listing_fossil_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 2: Details of transaction of digital literacy sessions"
    # awc_id = CC_AWC_DL.objects.filter(status=1, user=request.user).values_list('awc__id')
    digital_literacy = DLSession.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, digital_literacy)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/fossil/digital_literacy/digital_literacy_listing.html', locals())


@ login_required(login_url='/login/')
def add_digital_literacy_fossil_cc_report(request, task_id):
    heading = "Section 2: ADD of transaction of digital literacy sessions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_DL.objects.filter(status=1, user=request.user).values_list('awc__id')
    digital_literacy = DLSession.objects.filter(task__id = task_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    fossil_dl_session_category_obj =  FossilDLSessionConfig.objects.filter(status=1,)
    
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_selected_id = data.get('awc_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_dl_session_config_id = data.get('fossil_dl_session_config')
        fossil_dl_session_config = FossilDLSessionConfig.objects.get(id=fossil_dl_session_config_id)
        session_name = data.get('session_name')
        date_of_session = data.get('date_of_session')
        age = data.get('age')
        gender = data.get('gender')
        facilitator_name = data.get('facilitator_name')
        designations = data.get('designations')
        adolescent_obj =  Adolescent.objects.filter(awc__id=adolescent_selected_id, site=current_site)
        session_day = data.get('session_day')
        task = Task.objects.get(id=task_id)
        if DLSession.objects.filter(adolescent_name=adolescent_name, fossil_dl_session_config=fossil_dl_session_config,
                                    date_of_session=date_of_session,  status=1).exists():
            exist_error = "This data already exist!!!"
            return render(request, 'cc_report/fossil/digital_literacy/add_digital_literacy.html', locals())
        else:  
            digital_literacy = DLSession.objects.create(adolescent_name=adolescent_name, age=age or None, gender=gender or None,
            facilitator_name=facilitator_name, designation_data=designations, fossil_dl_session_config=fossil_dl_session_config,
            date_of_session=date_of_session, session_name=session_name, session_day=session_day, task=task, site_id = current_site)
            digital_literacy.save()
        return redirect('/cc-report/fossil/digital-literacy-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/digital_literacy/add_digital_literacy.html', locals())


@ login_required(login_url='/login/')
def edit_digital_literacy_fossil_cc_report(request, dlsession_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 2: Edit of transaction of digital literacy sessions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_DL.objects.filter(status=1, user=request.user).values_list('awc__id')
    digital_literacy = DLSession.objects.get(id=dlsession_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id=digital_literacy.adolescent_name.awc.id, site=current_site)
    fossil_dl_session_category_obj =  FossilDLSessionConfig.objects.filter(status=1,)

    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_dl_session_config_id = data.get('fossil_dl_session_config')
        fossil_dl_session_config = FossilDLSessionConfig.objects.get(id=fossil_dl_session_config_id)
        session_name = data.get('session_name')
        age = data.get('age')
        gender = data.get('gender')
        facilitator_name = data.get('facilitator_name')
        designations = data.get('designations')
        date_of_session = data.get('date_of_session')
        session_day = data.get('session_day')
        task = Task.objects.get(id=task_id)
        if DLSession.objects.filter(adolescent_name=adolescent_name, fossil_dl_session_config=fossil_dl_session_config,
                                    date_of_session=date_of_session,  status=1).exclude(id=dlsession_id).exists():
            exist_error = "This data already exist!!!"
            return render(request, 'cc_report/fossil/digital_literacy/edit_digital_literacy.html', locals())
        else:
            digital_literacy.adolescent_name_id = adolescent_name
            digital_literacy.fossil_dl_session_config_id = fossil_dl_session_config
            digital_literacy.date_of_session = date_of_session
            digital_literacy.session_name = session_name
            digital_literacy.age = age or None
            digital_literacy.gender = gender or None
            digital_literacy.facilitator_name = facilitator_name
            digital_literacy.designation_data = designations
            digital_literacy.session_day = session_day
            digital_literacy.task_id = task
            digital_literacy.site_id =  current_site
            digital_literacy.save()
        return redirect('/cc-report/fossil/digital-literacy-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/digital_literacy/edit_digital_literacy.html', locals())


@ login_required(login_url='/login/')
def girls_ahwd_listing_fossil_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 4(a): Details of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    # school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, girls_ahwd)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/fossil/girls_ahwd/girls_ahwd_listing.html', locals())


@ login_required(login_url='/login/')
def add_girls_ahwd_fossil_cc_report(request, task_id):
    heading = "Section 4(a): Add of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.filter(task__id = task_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
  
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')

        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        tt_10_14_years = data.get('tt_10_14_years')
        tt_15_19_years = data.get('tt_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)
        

        girls_ahwd = GirlsAHWD.objects.create(place_of_ahwd=place_of_ahwd, content_type=content_type, object_id=selected_object_id,
        participated_10_14_years=participated_10_14_years, date_of_ahwd=date_of_ahwd, hwc_name=hwc_name,
        participated_15_19_years=participated_15_19_years, bmi_10_14_years=bmi_10_14_years,
        bmi_15_19_years=bmi_15_19_years, hb_10_14_years=hb_10_14_years, hb_15_19_years=hb_15_19_years,
        tt_10_14_years=tt_10_14_years, tt_15_19_years=tt_15_19_years, counselling_10_14_years=counselling_10_14_years,
        counselling_15_19_years=counselling_15_19_years, referral_10_14_years=referral_10_14_years,
        referral_15_19_years=referral_15_19_years, task=task, site_id = current_site)
        girls_ahwd.save()
        return redirect('/cc-report/fossil/girls-ahwd-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/girls_ahwd/add_girls_ahwd.html', locals())


@ login_required(login_url='/login/')
def edit_girls_ahwd_fossil_cc_report(request, girls_ahwd_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 4(a): Edit of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.get(id=girls_ahwd_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
  
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
            
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        tt_10_14_years = data.get('tt_10_14_years')
        tt_15_19_years = data.get('tt_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)
        

        girls_ahwd.place_of_ahwd = place_of_ahwd
        girls_ahwd.content_type = content_type
        girls_ahwd.object_id = selected_object_id
        girls_ahwd.hwc_name = hwc_name
        girls_ahwd.date_of_ahwd = date_of_ahwd
        girls_ahwd.participated_10_14_years = participated_10_14_years
        girls_ahwd.participated_15_19_years = participated_15_19_years
        girls_ahwd.bmi_10_14_years = bmi_10_14_years
        girls_ahwd.bmi_15_19_years = bmi_15_19_years
        girls_ahwd.hb_10_14_years = hb_10_14_years
        girls_ahwd.hb_15_19_years = hb_15_19_years
        girls_ahwd.tt_10_14_years = tt_10_14_years
        girls_ahwd.tt_15_19_years = tt_15_19_years
        girls_ahwd.counselling_10_14_years = counselling_10_14_years
        girls_ahwd.counselling_15_19_years = counselling_15_19_years
        girls_ahwd.referral_10_14_years = referral_10_14_years
        girls_ahwd.referral_15_19_years = referral_15_19_years
        girls_ahwd.task_id = task
        girls_ahwd.site_id =  current_site
        girls_ahwd.save()
        return redirect('/cc-report/fossil/girls-ahwd-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/girls_ahwd/edit_girls_ahwd.html', locals())




@ login_required(login_url='/login/')
def boys_ahwd_listing_fossil_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 4(b): Details of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    # school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.filter( status=1, task__id = task_id)
    data = pagination_function(request, boys_ahwd)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/fossil/boys_ahwd/boys_ahwd_listing.html', locals())


@ login_required(login_url='/login/')
def add_boys_ahwd_fossil_cc_report(request, task_id):
    heading = "Section 4(b): Add of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.filter(status=1, task__id = task_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name') 
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)
       

        boys_ahwd = BoysAHWD.objects.create(place_of_ahwd=place_of_ahwd, content_type=content_type, object_id=selected_object_id,
        participated_10_14_years=participated_10_14_years, date_of_ahwd=date_of_ahwd,  hwc_name=hwc_name,
        participated_15_19_years=participated_15_19_years, bmi_10_14_years=bmi_10_14_years,
        bmi_15_19_years=bmi_15_19_years, hb_10_14_years=hb_10_14_years, hb_15_19_years=hb_15_19_years,
        counselling_10_14_years=counselling_10_14_years,
        counselling_15_19_years=counselling_15_19_years, referral_10_14_years=referral_10_14_years,
        referral_15_19_years=referral_15_19_years, task=task, site_id = current_site)
        boys_ahwd.save()
        return redirect('/cc-report/fossil/boys-ahwd-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/boys_ahwd/add_boys_ahwd.html', locals())


@ login_required(login_url='/login/')
def edit_boys_ahwd_fossil_cc_report(request, boys_ahwd_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 4(b): Edit of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.get(id=boys_ahwd_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        boys_ahwd.place_of_ahwd = place_of_ahwd
        boys_ahwd.content_type = content_type
        boys_ahwd.object_id = selected_object_id
        boys_ahwd.hwc_name = hwc_name
        boys_ahwd.date_of_ahwd = date_of_ahwd
        boys_ahwd.participated_10_14_years = participated_10_14_years
        boys_ahwd.participated_15_19_years = participated_15_19_years
        boys_ahwd.bmi_10_14_years = bmi_10_14_years
        boys_ahwd.bmi_15_19_years = bmi_15_19_years
        boys_ahwd.hb_10_14_years = hb_10_14_years
        boys_ahwd.hb_15_19_years = hb_15_19_years
        boys_ahwd.counselling_10_14_years = counselling_10_14_years
        boys_ahwd.counselling_15_19_years = counselling_15_19_years
        boys_ahwd.referral_10_14_years = referral_10_14_years
        boys_ahwd.referral_15_19_years = referral_15_19_years
        boys_ahwd.task_id = task
        boys_ahwd.site_id =  current_site
        boys_ahwd.save()
        return redirect('/cc-report/fossil/boys-ahwd-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/boys_ahwd/edit_boys_ahwd.html', locals())




@ login_required(login_url='/login/')
def vocation_listing_fossil_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 3: Details of adolescent linked with vocational training & placement"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    # awc = AWC.objects.filter(status=1, id__in=awc_id)
    
    vocation_obj =  AdolescentVocationalTraining.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, vocation_obj)
    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/fossil/voctional_training/vocation_listing.html', locals())

@ login_required(login_url='/login/')
def add_vocation_fossil_cc_report(request, task_id):
    heading = "Section 3: Add of adolescent linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.filter(status=1, task__id = task_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site, age_in_completed_years__gte=18).order_by('name')
    tranining_sub_obj = TrainingSubject.objects.all()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id=training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)
        
        vocation_obj = AdolescentVocationalTraining.objects.create(adolescent_name=adolescent_name, date_of_registration=date_of_registration, 
        age=age or None, parent_guardian_name=parent_guardian_name, training_subject=training_subject,
        training_providing_by=training_providing_by, duration_days=duration_days, training_complated=training_complated, 
        placement_offered=placement_offered or None, placement_accepted=placement_accepted or None, type_of_employment=type_of_employment or None,
        task=task, site_id = current_site)
        vocation_obj.save()
        return redirect('/cc-report/fossil/vocation-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/voctional_training/add_vocation_training.html', locals())


@ login_required(login_url='/login/')
def edit_vocation_fossil_cc_report(request, vocation_id,task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 3: Edit of adolescent linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.get(id=vocation_id)
    adolescent_obj =  Adolescent.objects.filter(awc__id__in=awc_id, site=current_site, age_in_completed_years__gte=18).order_by('name')
    tranining_sub_obj = TrainingSubject.objects.all()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id = training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered') 
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)

        vocation_obj.adolescent_name_id = adolescent_name
        vocation_obj.date_of_registration = date_of_registration
        vocation_obj.age = age or None
        vocation_obj.parent_guardian_name = parent_guardian_name
        vocation_obj.training_subject = training_subject
        vocation_obj.training_providing_by = training_providing_by
        vocation_obj.duration_days = duration_days
        vocation_obj.training_complated = training_complated
        vocation_obj.placement_offered = placement_offered or None
        vocation_obj.placement_accepted = placement_accepted or None
        vocation_obj.type_of_employment = type_of_employment or None
        vocation_obj.task_id = task
        vocation_obj.site_id =  current_site
        vocation_obj.save()
        return redirect('/cc-report/fossil/vocation-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/voctional_training/edit_vocation_training.html', locals())


@ login_required(login_url='/login/')
def adolescents_referred_listing_fossil_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 5: Details of adolescents referred"
    current_site = request.session.get('site_id')
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, adolescents_referred)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/fossil/adolescent_referred/adolescent_referred_listing.html', locals())

@ login_required(login_url='/login/')
def add_adolescents_referred_fossil_cc_report(request, task_id):
    heading = "Section 5: Add of adolescents referred"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.filter(status=1)
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_referred_10_14_year = data.get('girls_referred_10_14_year')
        girls_referred_15_19_year = data.get('girls_referred_15_19_year')
        boys_referred_10_14_year = data.get('boys_referred_10_14_year')
        boys_referred_15_19_year = data.get('boys_referred_15_19_year')
        girls_hwc_referred = data.get('girls_hwc_referred')
        girls_hwc_visited = data.get('girls_hwc_visited')
        girls_afhc_referred = data.get('girls_afhc_referred')
        girls_afhc_visited = data.get('girls_afhc_visited')
        girls_dh_referred = data.get('girls_dh_referred')
        girls_dh_visited = data.get('girls_dh_visited')
        boys_hwc_referred = data.get('boys_hwc_referred')
        boys_hwc_visited = data.get('boys_hwc_visited')
        boys_afhc_referred = data.get('boys_afhc_referred')
        boys_afhc_visited = data.get('boys_afhc_visited')
        boys_dh_referred = data.get('boys_dh_referred')
        boys_dh_visited = data.get('boys_dh_visited')
        task = Task.objects.get(id=task_id)

        adolescents_referred = AdolescentsReferred.objects.create(awc_name=awc_name, girls_referred_10_14_year=girls_referred_10_14_year, 
        girls_referred_15_19_year=girls_referred_15_19_year, boys_referred_10_14_year=boys_referred_10_14_year, boys_referred_15_19_year=boys_referred_15_19_year,
        girls_hwc_referred=girls_hwc_referred, girls_hwc_visited=girls_hwc_visited, girls_afhc_referred=girls_afhc_referred, girls_afhc_visited=girls_afhc_visited,
        girls_dh_referred=girls_dh_referred, girls_dh_visited=girls_dh_visited, boys_hwc_referred=boys_hwc_referred, boys_hwc_visited=boys_hwc_visited,
        boys_afhc_referred=boys_afhc_referred, boys_afhc_visited=boys_afhc_visited, 
        boys_dh_referred=boys_dh_referred, boys_dh_visited=boys_dh_visited, task=task, site_id = current_site)
        adolescents_referred.save()
        return redirect('/cc-report/fossil/adolescent-referred-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/adolescent_referred/add_adolescen_referred.html', locals())


@ login_required(login_url='/login/')
def edit_adolescents_referred_fossil_cc_report(request, adolescents_referred_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 5: Edit of adolescents referred"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.get(id=adolescents_referred_id)
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_referred_10_14_year = data.get('girls_referred_10_14_year')
        girls_referred_15_19_year = data.get('girls_referred_15_19_year')
        boys_referred_10_14_year = data.get('boys_referred_10_14_year')
        boys_referred_15_19_year = data.get('boys_referred_15_19_year')
        girls_hwc_referred = data.get('girls_hwc_referred')
        girls_hwc_visited = data.get('girls_hwc_visited')
        girls_afhc_referred = data.get('girls_afhc_referred')
        girls_afhc_visited = data.get('girls_afhc_visited')
        girls_dh_referred = data.get('girls_dh_referred')
        girls_dh_visited = data.get('girls_dh_visited')
        boys_hwc_referred = data.get('boys_hwc_referred')
        boys_hwc_visited = data.get('boys_hwc_visited')
        boys_afhc_referred = data.get('boys_afhc_referred')
        boys_afhc_visited = data.get('boys_afhc_visited')
        boys_dh_referred = data.get('boys_dh_referred')
        boys_dh_visited = data.get('boys_dh_visited')  
        task = Task.objects.get(id=task_id)

        adolescents_referred.awc_name_id = awc_name
        adolescents_referred.girls_referred_10_14_year = girls_referred_10_14_year
        adolescents_referred.girls_referred_15_19_year = girls_referred_15_19_year
        adolescents_referred.boys_referred_10_14_year = boys_referred_10_14_year
        adolescents_referred.boys_referred_15_19_year = boys_referred_15_19_year
        adolescents_referred.girls_hwc_referred = girls_hwc_referred
        adolescents_referred.girls_hwc_visited = girls_hwc_visited
        adolescents_referred.girls_afhc_referred = girls_afhc_referred
        adolescents_referred.girls_afhc_visited = girls_afhc_visited
        adolescents_referred.girls_dh_referred = girls_dh_referred
        adolescents_referred.girls_dh_visited = girls_dh_visited
        adolescents_referred.boys_hwc_referred = boys_hwc_referred
        adolescents_referred.boys_hwc_visited = boys_hwc_visited
        adolescents_referred.boys_afhc_referred = boys_afhc_referred
        adolescents_referred.boys_afhc_visited = boys_afhc_visited
        adolescents_referred.boys_dh_referred = boys_dh_referred
        adolescents_referred.boys_dh_visited = boys_dh_visited
        adolescents_referred.task_id = task
        adolescents_referred.site_id =  current_site
        adolescents_referred.save()
        return redirect('/cc-report/fossil/adolescent-referred-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/adolescent_referred/edit_adolescent_referred.html', locals())



@ login_required(login_url='/login/')
def friendly_club_listing_fossil_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 6: Details of Adolescent Friendly Club (AFC)"
    # panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, friendly_club)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/fossil/friendly_club/friendly_club_listing.html', locals())

@ login_required(login_url='/login/')
def add_friendly_club_fossil_cc_report(request, task_id):
    heading = "Section 6: Add of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(status=1)
    gramapanchayat = GramaPanchayat.objects.filter(status=1, id__in=panchayat_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        panchayat_name_id = data.get('panchayat_name')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        date_of_registration = data.get('date_of_registration')
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)

        friendly_club = AdolescentFriendlyClub.objects.create(panchayat_name=panchayat_name,
        start_date = date_of_registration, hsc_name=hsc_name, subject=subject, facilitator=facilitator, designation=designation,
        no_of_sahiya=no_of_sahiya, no_of_aww=no_of_aww, pe_girls_10_14_year=pe_girls_10_14_year,
        pe_girls_15_19_year=pe_girls_15_19_year, pe_boys_10_14_year=pe_boys_10_14_year,
        pe_boys_15_19_year=pe_boys_15_19_year, task=task, site_id = current_site)
        friendly_club.save()
        return redirect('/cc-report/fossil/friendly-club-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/friendly_club/add_friendly_club.html', locals())



@ login_required(login_url='/login/')
def edit_friendly_club_fossil_cc_report(request, friendly_club_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 6: Edit of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.get(id=friendly_club_id)
    gramapanchayat = GramaPanchayat.objects.filter(status=1, id__in=panchayat_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        panchayat_name_id = data.get('panchayat_name')
        date_of_registration = data.get('date_of_registration')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)
       

        friendly_club.panchayat_name_id = panchayat_name
        friendly_club.start_date = date_of_registration
        friendly_club.hsc_name = hsc_name
        friendly_club.subject = subject
        friendly_club.facilitator = facilitator
        friendly_club.designation = designation
        friendly_club.no_of_sahiya = no_of_sahiya
        friendly_club.no_of_aww = no_of_aww
        friendly_club.pe_girls_10_14_year = pe_girls_10_14_year
        friendly_club.pe_girls_15_19_year = pe_girls_15_19_year
        friendly_club.pe_boys_10_14_year = pe_boys_10_14_year
        friendly_club.pe_boys_15_19_year = pe_boys_15_19_year
        friendly_club.task_id = task
        friendly_club.site_id =  current_site
        friendly_club.save()
        return redirect('/cc-report/fossil/friendly-club-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/friendly_club/edit_friendly_club.html', locals())


@ login_required(login_url='/login/')
def balsansad_meeting_listing_fossil_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 7: Details of Bal Sansad meetings conducted"
    # school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, balsansad_meeting)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/fossil/bal_sansad_metting/bal_sansad_listing.html', locals())

@ login_required(login_url='/login/')
def add_balsansad_meeting_fossil_cc_report(request, task_id):
    heading = "Section 7: Add of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.filter()
    school = School.objects.filter(status=1, id__in=school_id).order_by('name')
    masterlookups_issues_discussion = MasterLookUp.objects.filter(parent__slug = 'issues_discussion')

    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        school_name_id = data.get('school_name')
        school_name = School.objects.get(id=school_name_id)
        no_of_participants = data.get('no_of_participants')
        issues_discussion = data.get('issues_discussion')
        decision_taken = data.get('decision_taken')
        task = Task.objects.get(id=task_id)
        balsansad_meeting = BalSansadMeeting.objects.create(start_date = date_of_registration, school_name = school_name,
        no_of_participants=no_of_participants,   decision_taken=decision_taken,
        task=task, site_id =  current_site)

        if issues_discussion:
            issues_discussion = MasterLookUp.objects.get(id=issues_discussion)
            balsansad_meeting.issues_discussion = issues_discussion

        balsansad_meeting.save()
        return redirect('/cc-report/fossil/balsansad-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/bal_sansad_metting/add_bal_sansad.html', locals())


@ login_required(login_url='/login/')
def edit_balsansad_meeting_fossil_cc_report(request, balsansad_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 7: Edit of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.get(id=balsansad_id)
    school = School.objects.filter(status=1, id__in=school_id).order_by('name')
    masterlookups_issues_discussion = MasterLookUp.objects.filter(parent__slug = 'issues_discussion')

    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        school_name_id = data.get('school_name')
        school_name = School.objects.get(id=school_name_id)
        no_of_participants = data.get('no_of_participants')
        issues_discussion = data.get('issues_discussion')
        decision_taken = data.get('decision_taken')
        task = Task.objects.get(id=task_id)
        balsansad_meeting.start_date = date_of_registration
        balsansad_meeting.school_name_id = school_name
        balsansad_meeting.no_of_participants = no_of_participants
        balsansad_meeting.decision_taken = decision_taken
        balsansad_meeting.task_id = task
        balsansad_meeting.site_id =  current_site
        if issues_discussion:
            issues_discussion = MasterLookUp.objects.get(id=issues_discussion)
            balsansad_meeting.issues_discussion = issues_discussion
        balsansad_meeting.save()
        return redirect('/cc-report/fossil/balsansad-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/bal_sansad_metting/edit_bal_sansad.html', locals())


@ login_required(login_url='/login/')
def community_activities_listing_fossil_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 8: Details of community engagement activities"
    # village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, activities)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/fossil/community_activities/community_activities_listing.html', locals())


@ login_required(login_url='/login/')
def add_community_activities_fossil_cc_report(request, task_id):
    heading = "Section 8: Add of community engagement activities"
    current_site = request.session.get('site_id')
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.filter(status=1,)
    village =  Village.objects.filter(status=1, id__in=village_id).order_by('name')
    masterlookups_event = MasterLookUp.objects.filter(parent__slug = 'event')
    masterlookups_activity = MasterLookUp.objects.filter(parent__slug = 'activities')

    if request.method == 'POST':
        data = request.POST
        village_name_id = data.get('village_name')
        date_of_registration = data.get('date_of_registration')
        village_name = Village.objects.get(id=village_name_id)
        name_of_event_id = data.get('name_of_event')
        name_of_activity_id = data.get('name_of_activity') 
        name_of_event_activity = data.get('name_of_event_activity')
        organized_by = data.get('organized_by')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)

        activities =  CommunityEngagementActivities.objects.create(village_name=village_name, start_date = date_of_registration,
        name_of_event_activity=name_of_event_activity, organized_by=organized_by,
        girls_10_14_year=girls_10_14_year, girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year,
        boys_15_19_year=boys_15_19_year, champions_15_19_year=champions_15_19_year, adult_male=adult_male,
        adult_female=adult_female, teachers=teachers, pri_members=pri_members, services_providers=services_providers,
        sms_members=sms_members, other=other, task=task, site_id = current_site)
        
        if name_of_event_id:
            name_of_event = MasterLookUp.objects.get(id=name_of_event_id)
            activities.event_name = name_of_event

        if name_of_activity_id:
            name_of_activity = MasterLookUp.objects.get(id=name_of_activity_id)
            activities.activity_name = name_of_activity

        activities.save()
        return redirect('/cc-report/fossil/community-activities-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/community_activities/add_community_activities.html', locals())


@ login_required(login_url='/login/')
def edit_community_activities_fossil_cc_report(request, activities_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 8: Edit of community engagement activities"
    current_site = request.session.get('site_id')
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.get(id=activities_id)
    village =  Village.objects.filter(status=1, id__in=village_id).order_by('name')
    masterlookups_event = MasterLookUp.objects.filter(parent__slug = 'event')
    masterlookups_activity = MasterLookUp.objects.filter(parent__slug = 'activities')

    if request.method == 'POST':
        data = request.POST
        village_name_id = data.get('village_name')
        date_of_registration = data.get('date_of_registration')
        village_name = Village.objects.get(id=village_name_id)
        name_of_event_activity = data.get('name_of_event_activity')
        # theme_topic = data.get('theme_topic')
        name_of_event_id = data.get('name_of_event')
        name_of_activity_id = data.get('name_of_activity')

        organized_by = data.get('organized_by')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)

        activities.start_date = date_of_registration
        activities.village_name_id = village_name
        activities.name_of_event_activity = name_of_event_activity
        # activities.theme_topic = theme_topic
        activities.organized_by = organized_by
        activities.boys_10_14_year = boys_10_14_year
        activities.boys_15_19_year = boys_15_19_year
        activities.girls_10_14_year = girls_10_14_year
        activities.girls_15_19_year = girls_15_19_year
        activities.champions_15_19_year = champions_15_19_year
        activities.adult_male = adult_male
        activities.adult_female = adult_female
        activities.teachers = teachers
        activities.pri_members = pri_members
        activities.services_providers = services_providers
        activities.sms_members = sms_members
        activities.other = other
        activities.task_id = task
        activities.site_id =  current_site
        
        if name_of_event_id:
            name_of_event = MasterLookUp.objects.get(id = name_of_event_id)
            activities.event_name = name_of_event

        if name_of_activity_id:
            name_of_activity = MasterLookUp.objects.get(id = name_of_activity_id)
            activities.activity_name = name_of_activity
        activities.save()
        return redirect('/cc-report/fossil/community-activities-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/community_activities/edit_community_activities.html', locals())





@ login_required(login_url='/login/')
def champions_listing_fossil_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 9: Details of exposure visits of adolescent champions"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, champions)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/fossil/champions/champions_listing.html', locals())

@ login_required(login_url='/login/')
def add_champions_fossil_cc_report(request, task_id):
    heading = "Section 9: Add of exposure visits of adolescent champions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.filter(status=1,)
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        date_of_visit = data.get('date_of_visit')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        first_inst_visited = data.get('first_inst_visited')
        second_inst_visited = data.get('second_inst_visited')
        third_inst_visited = data.get('third_inst_visited')
        fourth_inst_visited = data.get('fourth_inst_visited')
        task = Task.objects.get(id=task_id)

        champions =  Champions.objects.create(awc_name=awc_name, date_of_visit=date_of_visit, girls_10_14_year=girls_10_14_year,
        girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year, boys_15_19_year=boys_15_19_year,
        first_inst_visited=first_inst_visited,second_inst_visited=second_inst_visited or None,
        third_inst_visited=third_inst_visited or None, fourth_inst_visited=fourth_inst_visited or None, task=task, site_id = current_site)
        champions.save()
        return redirect('/cc-report/fossil/champions-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/champions/add_champions.html', locals())


@ login_required(login_url='/login/')
def edit_champions_fossil_cc_report(request, champions_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 9: Edit of exposure visits of adolescent champions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.get(id=champions_id)
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        date_of_visit = data.get('date_of_visit')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        first_inst_visited = data.get('first_inst_visited')
        second_inst_visited = data.get('second_inst_visited')
        third_inst_visited = data.get('third_inst_visited')
        fourth_inst_visited = data.get('fourth_inst_visited')
        task = Task.objects.get(id=task_id)

        champions.awc_name_id = awc_name       
        champions.date_of_visit = date_of_visit       
        champions.girls_10_14_year = girls_10_14_year       
        champions.girls_15_19_year = girls_15_19_year     
        champions.boys_10_14_year = boys_10_14_year       
        champions.boys_15_19_year = boys_15_19_year       
        champions.first_inst_visited = first_inst_visited
        champions.second_inst_visited= second_inst_visited or None
        champions.third_inst_visited = third_inst_visited or None
        champions.fourth_inst_visited = fourth_inst_visited or None
        champions.task_id = task
        champions.site_id =  current_site       
        champions.save()
        return redirect('/cc-report/fossil/champions-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/champions/edit_champions.html', locals())

@ login_required(login_url='/login/')
def reenrolled_listing_fossil_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 10: Details of adolescent re-enrolled in schools"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, adolescent_reenrolled)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/fossil/re_enrolled/re_enrolled_listing.html', locals())

@ login_required(login_url='/login/')
def add_reenrolled_fossil_cc_report(request, task_id):
    heading = "Section 10: Add of adolescent re-enrolled in schools"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter()
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site).order_by('name')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    # school = School.objects.filter(status=1, id__in = school_id)
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        gender = data.get('gender')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        school_name = data.get('school_name')
        # school_name = School.objects.get(id=school_name_id)
        which_class_enrolled = data.get('which_class_enrolled')
        task = Task.objects.get(id=task_id)

        adolescent_reenrolled =  AdolescentRe_enrolled.objects.create(adolescent_name=adolescent_name,
        gender=gender or None, age=age or None, parent_guardian_name=parent_guardian_name, school_name=school_name, which_class_enrolled=which_class_enrolled,
        task=task, site_id = current_site)
        adolescent_reenrolled.save()
        return redirect('/cc-report/fossil/reenrolled-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/re_enrolled/add_re_enrolled.html', locals())


@ login_required(login_url='/login/')
def edit_reenrolled_fossil_cc_report(request, reenrolled_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 10: Edit of adolescent re-enrolled in schools"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.get(id=reenrolled_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site).order_by('name')
    # school = School.objects.filter()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        gender = data.get('gender')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        school_name = data.get('school_name')
        # school_name = School.objects.get(id=school_name_id)
        which_class_enrolled = data.get('which_class_enrolled')
        task = Task.objects.get(id=task_id)

        adolescent_reenrolled.adolescent_name_id = adolescent_name
        adolescent_reenrolled.gender = gender or None
        adolescent_reenrolled.age = age or None
        adolescent_reenrolled.parent_guardian_name = parent_guardian_name
        adolescent_reenrolled.school_name = school_name
        adolescent_reenrolled.which_class_enrolled = which_class_enrolled
        adolescent_reenrolled.task_id = task
        adolescent_reenrolled.site_id =  current_site
        adolescent_reenrolled.save()
        return redirect('/cc-report/fossil/reenrolled-listing/'+str(task_id))
    return render(request, 'cc_report/fossil/re_enrolled/edit_re_enrolled.html', locals())


#-----------cc-report  rnp---------------






@ login_required(login_url='/login/')
def health_sessions_listing_rnp_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 1: Details of transaction of sessions on health & nutrition"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, health_sessions)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/rnp/health_sessions/health_sessions_listing.html', locals())

@ login_required(login_url='/login/')
def add_health_sessions_rnp_cc_report(request, task_id):
    heading = "Section 1: Add of transaction of sessions on health & nutrition"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.filter(status=1)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    fossil_ah_session_category_obj =  FossilAHSessionCategory.objects.filter(status=1)
  
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_selected_id = data.get('awc_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_ah_session_id = data.get('fossil_ah_session')
        age = data.get('age')
        gender = data.get('gender')
        fossil_ah_session_selected_id = data.get('fossil_ah_session_category')
        fossil_ah_session = FossilAHSession.objects.get(id=fossil_ah_session_id)
        date_of_session = data.get('date_of_session')
        adolescent_obj =  Adolescent.objects.filter(awc__id=adolescent_selected_id, site=current_site)
        fossil_ah_session_obj =  FossilAHSession.objects.filter(fossil_ah_session_category__id = fossil_ah_session_selected_id)
        session_day = data.get('session_day')
        facilitator_name = data.get('facilitator_name')
        designations = data.get('designations')
        task = Task.objects.get(id=task_id)
        if AHSession.objects.filter(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
                                    date_of_session=date_of_session,  status=1).exists():
            exist_error = "Please try again this data already exists!!!"
            return render(request,'cc_report/rnp/health_sessions/add_health_sessions.html', locals())
        else:
            health_sessions = AHSession.objects.create(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
            date_of_session=date_of_session, session_day=session_day, designation_data = designations,
            age = age or None, gender=gender or None, facilitator_name = facilitator_name, task=task, site_id = current_site)
            health_sessions.save()
        return redirect('/cc-report/rnp/health-sessions-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/health_sessions/add_health_sessions.html', locals())

@ login_required(login_url='/login/')
def edit_health_sessions_rnp_cc_report(request, ahsession_id, task_id):
    heading = "Section 1: Edit of transaction of sessions on health & nutrition"
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.get(id=ahsession_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id=health_sessions.adolescent_name.awc.id, site=current_site)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    fossil_ah_session_obj =  FossilAHSession.objects.filter(status=1, fossil_ah_session_category__id=health_sessions.fossil_ah_session.fossil_ah_session_category.id)
    fossil_ah_session_category_obj =  FossilAHSessionCategory.objects.filter(status=1,)
    
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_ah_session_id = data.get('fossil_ah_session')
        fossil_ah_session = FossilAHSession.objects.get(id=fossil_ah_session_id)
        date_of_session = data.get('date_of_session')
        age = data.get('age')
        gender = data.get('gender')
        session_day = data.get('session_day')
        facilitator_name = data.get('facilitator_name')
        designations = data.get('designations')
        task = Task.objects.get(id=task_id)
        if AHSession.objects.filter(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
                                    date_of_session=date_of_session,  status=1).exclude(id=ahsession_id).exists():
            exist_error = "Please try again this data already exists!!!"
            return render(request,'cc_report/rnp/health_sessions/edit_health_sessions.html', locals())
        else:
            health_sessions.adolescent_name_id = adolescent_name
            health_sessions.fossil_ah_session_id = fossil_ah_session
            health_sessions.date_of_session = date_of_session
            health_sessions.age = age or None
            health_sessions.gender = gender or None
            health_sessions.session_day = session_day
            health_sessions.designation_data = designations
            health_sessions.facilitator_name = facilitator_name
            health_sessions.task_id = task
            health_sessions.site_id =  current_site
            health_sessions.save()
        return redirect('/cc-report/rnp/health-sessions-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/health_sessions/edit_health_sessions.html', locals())


@ login_required(login_url='/login/')
def girls_ahwd_listing_rnp_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 3(a): Details of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    # school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, girls_ahwd)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/rnp/girls_ahwd/girls_ahwd_listing.html', locals())


@ login_required(login_url='/login/')
def add_girls_ahwd_rnp_cc_report(request, task_id):
    heading = "Section 3(a): Add of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model)  if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        tt_10_14_years = data.get('tt_10_14_years')
        tt_15_19_years = data.get('tt_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        girls_ahwd = GirlsAHWD.objects.create(place_of_ahwd=place_of_ahwd, content_type=content_type, object_id=selected_object_id,
        participated_10_14_years=participated_10_14_years, date_of_ahwd=date_of_ahwd, hwc_name=hwc_name,
        participated_15_19_years=participated_15_19_years, bmi_10_14_years=bmi_10_14_years,
        bmi_15_19_years=bmi_15_19_years, hb_10_14_years=hb_10_14_years, hb_15_19_years=hb_15_19_years,
        tt_10_14_years=tt_10_14_years, tt_15_19_years=tt_15_19_years, counselling_10_14_years=counselling_10_14_years,
        counselling_15_19_years=counselling_15_19_years, referral_10_14_years=referral_10_14_years,
        referral_15_19_years=referral_15_19_years, task=task, site_id = current_site)
        girls_ahwd.save()
        return redirect('/cc-report/rnp/girls-ahwd-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/girls_ahwd/add_girls_ahwd.html', locals())


@ login_required(login_url='/login/')
def edit_girls_ahwd_rnp_cc_report(request, girls_ahwd_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 3(a): Edit of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.get(id=girls_ahwd_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model)  if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        tt_10_14_years = data.get('tt_10_14_years')
        tt_15_19_years = data.get('tt_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        girls_ahwd.place_of_ahwd = place_of_ahwd
        girls_ahwd.content_type = content_type
        girls_ahwd.object_id = selected_object_id
        girls_ahwd.hwc_name = hwc_name
        girls_ahwd.date_of_ahwd = date_of_ahwd
        girls_ahwd.participated_10_14_years = participated_10_14_years
        girls_ahwd.participated_15_19_years = participated_15_19_years
        girls_ahwd.bmi_10_14_years = bmi_10_14_years
        girls_ahwd.bmi_15_19_years = bmi_15_19_years
        girls_ahwd.hb_10_14_years = hb_10_14_years
        girls_ahwd.hb_15_19_years = hb_15_19_years
        girls_ahwd.tt_10_14_years = tt_10_14_years
        girls_ahwd.tt_15_19_years = tt_15_19_years
        girls_ahwd.counselling_10_14_years = counselling_10_14_years
        girls_ahwd.counselling_15_19_years = counselling_15_19_years
        girls_ahwd.referral_10_14_years = referral_10_14_years
        girls_ahwd.referral_15_19_years = referral_15_19_years
        girls_ahwd.task_id = task
        girls_ahwd.site_id =  current_site
        girls_ahwd.save()
        return redirect('/cc-report/rnp/girls-ahwd-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/girls_ahwd/edit_girls_ahwd.html', locals())




@ login_required(login_url='/login/')
def boys_ahwd_listing_rnp_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 3(b): Details of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    # school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, boys_ahwd)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/rnp/boys_ahwd/boys_ahwd_listing.html', locals())


@ login_required(login_url='/login/')
def add_boys_ahwd_rnp_cc_report(request, task_id):
    heading = "Section 3(b): Add of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        boys_ahwd = BoysAHWD.objects.create(place_of_ahwd=place_of_ahwd, content_type=content_type, object_id=selected_object_id,
        participated_10_14_years=participated_10_14_years, date_of_ahwd=date_of_ahwd, hwc_name=hwc_name,
        participated_15_19_years=participated_15_19_years, bmi_10_14_years=bmi_10_14_years,
        bmi_15_19_years=bmi_15_19_years, hb_10_14_years=hb_10_14_years, hb_15_19_years=hb_15_19_years,
        counselling_10_14_years=counselling_10_14_years,
        counselling_15_19_years=counselling_15_19_years, referral_10_14_years=referral_10_14_years,
        referral_15_19_years=referral_15_19_years, task=task, site_id = current_site)
        boys_ahwd.save()
        return redirect('/cc-report/rnp/boys-ahwd-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/boys_ahwd/add_boys_ahwd.html', locals())


@ login_required(login_url='/login/')
def edit_boys_ahwd_rnp_cc_report(request, boys_ahwd_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 3(b): Edit of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.get(id=boys_ahwd_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model)  if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        boys_ahwd.place_of_ahwd = place_of_ahwd
        boys_ahwd.content_type = content_type
        boys_ahwd.object_id = selected_object_id
        boys_ahwd.hwc_name = hwc_name
        boys_ahwd.date_of_ahwd = date_of_ahwd
        boys_ahwd.participated_10_14_years = participated_10_14_years
        boys_ahwd.participated_15_19_years = participated_15_19_years
        boys_ahwd.bmi_10_14_years = bmi_10_14_years
        boys_ahwd.bmi_15_19_years = bmi_15_19_years
        boys_ahwd.hb_10_14_years = hb_10_14_years
        boys_ahwd.hb_15_19_years = hb_15_19_years
        boys_ahwd.counselling_10_14_years = counselling_10_14_years
        boys_ahwd.counselling_15_19_years = counselling_15_19_years
        boys_ahwd.referral_10_14_years = referral_10_14_years
        boys_ahwd.referral_15_19_years = referral_15_19_years
        boys_ahwd.task_id = task
        boys_ahwd.site_id =  current_site
        boys_ahwd.save()
        return redirect('/cc-report/rnp/boys-ahwd-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/boys_ahwd/edit_boys_ahwd.html', locals())


@ login_required(login_url='/login/')
def vocation_listing_rnp_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 2: Details of adolescent boys linked with vocational training & placement"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, vocation_obj)
    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/rnp/voctional_training/vocation_listing.html', locals())

@ login_required(login_url='/login/')
def add_vocation_rnp_cc_report(request, task_id):
    heading = "Section 2: Add of adolescent boys linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.filter()
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site, age_in_completed_years__gte=18).order_by('name')
    tranining_sub_obj = TrainingSubject.objects.all()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id=training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)
        vocation_obj = AdolescentVocationalTraining.objects.create(adolescent_name=adolescent_name, date_of_registration=date_of_registration, 
        age=age or None, parent_guardian_name=parent_guardian_name, training_subject=training_subject,
        training_providing_by=training_providing_by, duration_days=duration_days, training_complated=training_complated, 
        placement_offered=placement_offered or None, placement_accepted=placement_accepted or None, type_of_employment=type_of_employment or None,
        task=task, site_id = current_site)
        vocation_obj.save()
        return redirect('/cc-report/rnp/vocation-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/voctional_training/add_vocation_training.html', locals())


@ login_required(login_url='/login/')
def edit_vocation_rnp_cc_report(request, vocation_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 2: Edit of adolescent boys linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.get(id=vocation_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site, age_in_completed_years__gte=18).order_by('name')
    tranining_sub_obj = TrainingSubject.objects.all()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id = training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)

        vocation_obj.adolescent_name_id = adolescent_name
        vocation_obj.date_of_registration = date_of_registration
        vocation_obj.age = age or None
        vocation_obj.parent_guardian_name = parent_guardian_name
        vocation_obj.training_subject = training_subject
        vocation_obj.training_providing_by = training_providing_by
        vocation_obj.duration_days = duration_days
        vocation_obj.training_complated = training_complated
        vocation_obj.placement_offered = placement_offered or None
        vocation_obj.placement_accepted = placement_accepted or None
        vocation_obj.type_of_employment = type_of_employment or None
        vocation_obj.task_id = task
        vocation_obj.site_id =  current_site
        vocation_obj.save()
        return redirect('/cc-report/rnp/vocation-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/voctional_training/edit_vocation_training.html', locals())


@ login_required(login_url='/login/')
def adolescents_referred_listing_rnp_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 4: Details of adolescents referred"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, adolescents_referred)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/rnp/adolescent_referred/adolescent_referred_listing.html', locals())

@ login_required(login_url='/login/')
def add_adolescents_referred_rnp_cc_report(request, task_id):
    heading = "Section 4: Add of adolescents referred"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.filter(status=1)
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_referred_10_14_year = data.get('girls_referred_10_14_year')
        girls_referred_15_19_year = data.get('girls_referred_15_19_year')
        boys_referred_10_14_year = data.get('boys_referred_10_14_year')
        boys_referred_15_19_year = data.get('boys_referred_15_19_year')
        girls_hwc_referred = data.get('girls_hwc_referred')
        girls_hwc_visited = data.get('girls_hwc_visited')
        girls_afhc_referred = data.get('girls_afhc_referred')
        girls_afhc_visited = data.get('girls_afhc_visited')
        girls_dh_referred = data.get('girls_dh_referred')
        girls_dh_visited = data.get('girls_dh_visited')
        boys_hwc_referred = data.get('boys_hwc_referred')
        boys_hwc_visited = data.get('boys_hwc_visited')
        boys_afhc_referred = data.get('boys_afhc_referred')
        boys_afhc_visited = data.get('boys_afhc_visited')
        boys_dh_referred = data.get('boys_dh_referred')
        boys_dh_visited = data.get('boys_dh_visited')
        task = Task.objects.get(id=task_id)
        adolescents_referred = AdolescentsReferred.objects.create(awc_name=awc_name, girls_referred_10_14_year=girls_referred_10_14_year, 
        girls_referred_15_19_year=girls_referred_15_19_year, boys_referred_10_14_year=boys_referred_10_14_year, boys_referred_15_19_year=boys_referred_15_19_year,
        girls_hwc_referred=girls_hwc_referred, girls_hwc_visited=girls_hwc_visited, girls_afhc_referred=girls_afhc_referred, girls_afhc_visited=girls_afhc_visited,
        girls_dh_referred=girls_dh_referred, girls_dh_visited=girls_dh_visited, boys_hwc_referred=boys_hwc_referred, boys_hwc_visited=boys_hwc_visited,
        boys_afhc_referred=boys_afhc_referred, boys_afhc_visited=boys_afhc_visited, 
        boys_dh_referred=boys_dh_referred, boys_dh_visited=boys_dh_visited, task=task, site_id = current_site)
        adolescents_referred.save()
        return redirect('/cc-report/rnp/adolescent-referred-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/adolescent_referred/add_adolescen_referred.html', locals())


@ login_required(login_url='/login/')
def edit_adolescents_referred_rnp_cc_report(request, adolescents_referred_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 4: Edit of adolescents referred"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.get(id=adolescents_referred_id)
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_referred_10_14_year = data.get('girls_referred_10_14_year')
        girls_referred_15_19_year = data.get('girls_referred_15_19_year')
        boys_referred_10_14_year = data.get('boys_referred_10_14_year')
        boys_referred_15_19_year = data.get('boys_referred_15_19_year')
        girls_hwc_referred = data.get('girls_hwc_referred')
        girls_hwc_visited = data.get('girls_hwc_visited')
        girls_afhc_referred = data.get('girls_afhc_referred')
        girls_afhc_visited = data.get('girls_afhc_visited')
        girls_dh_referred = data.get('girls_dh_referred')
        girls_dh_visited = data.get('girls_dh_visited')
        boys_hwc_referred = data.get('boys_hwc_referred')
        boys_hwc_visited = data.get('boys_hwc_visited')
        boys_afhc_referred = data.get('boys_afhc_referred')
        boys_afhc_visited = data.get('boys_afhc_visited')
        boys_dh_referred = data.get('boys_dh_referred')
        boys_dh_visited = data.get('boys_dh_visited')  
        task = Task.objects.get(id=task_id)

        adolescents_referred.awc_name_id = awc_name
        adolescents_referred.girls_referred_10_14_year = girls_referred_10_14_year
        adolescents_referred.girls_referred_15_19_year = girls_referred_15_19_year
        adolescents_referred.boys_referred_10_14_year = boys_referred_10_14_year
        adolescents_referred.boys_referred_15_19_year = boys_referred_15_19_year
        adolescents_referred.girls_hwc_referred = girls_hwc_referred
        adolescents_referred.girls_hwc_visited = girls_hwc_visited
        adolescents_referred.girls_afhc_referred = girls_afhc_referred
        adolescents_referred.girls_afhc_visited = girls_afhc_visited
        adolescents_referred.girls_dh_referred = girls_dh_referred
        adolescents_referred.girls_dh_visited = girls_dh_visited
        adolescents_referred.boys_hwc_referred = boys_hwc_referred
        adolescents_referred.boys_hwc_visited = boys_hwc_visited
        adolescents_referred.boys_afhc_referred = boys_afhc_referred
        adolescents_referred.boys_afhc_visited = boys_afhc_visited
        adolescents_referred.boys_dh_referred = boys_dh_referred
        adolescents_referred.boys_dh_visited = boys_dh_visited
        adolescents_referred.task_id = task
        adolescents_referred.site_id =  current_site
        adolescents_referred.save()
        return redirect('/cc-report/rnp/adolescent-referred-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/adolescent_referred/edit_adolescent_referred.html', locals())

@ login_required(login_url='/login/')
def friendly_club_listing_rnp_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 5: Details of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    # panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, friendly_club)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/rnp/friendly_club/friendly_club_listing.html', locals())

@ login_required(login_url='/login/')
def add_friendly_club_rnp_cc_report(request, task_id):
    heading = "Section 5: Add of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(status=1)
    gramapanchayat = GramaPanchayat.objects.filter(status=1, id__in=panchayat_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        panchayat_name_id = data.get('panchayat_name')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)

        friendly_club = AdolescentFriendlyClub.objects.create(panchayat_name=panchayat_name,
        hsc_name=hsc_name, subject=subject, start_date=date_of_registration, facilitator=facilitator, designation=designation,
        no_of_sahiya=no_of_sahiya, no_of_aww=no_of_aww, pe_girls_10_14_year=pe_girls_10_14_year,
        pe_girls_15_19_year=pe_girls_15_19_year, pe_boys_10_14_year=pe_boys_10_14_year,
        pe_boys_15_19_year=pe_boys_15_19_year, task=task, site_id = current_site)
        friendly_club.save()
        return redirect('/cc-report/rnp/friendly-club-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/friendly_club/add_friendly_club.html', locals())



@ login_required(login_url='/login/')
def edit_friendly_club_rnp_cc_report(request, friendly_club_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 5: Edit of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.get(id=friendly_club_id)
    gramapanchayat = GramaPanchayat.objects.filter(status=1, id__in=panchayat_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        panchayat_name_id = data.get('panchayat_name')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)
        friendly_club.start_date = date_of_registration

        friendly_club.panchayat_name_id = panchayat_name
        friendly_club.hsc_name = hsc_name
        friendly_club.subject = subject
        friendly_club.facilitator = facilitator
        friendly_club.designation = designation
        friendly_club.no_of_sahiya = no_of_sahiya
        friendly_club.no_of_aww = no_of_aww
        friendly_club.pe_girls_10_14_year = pe_girls_10_14_year
        friendly_club.pe_girls_15_19_year = pe_girls_15_19_year
        friendly_club.pe_boys_10_14_year = pe_boys_10_14_year
        friendly_club.pe_boys_15_19_year = pe_boys_15_19_year
        friendly_club.task_id = task
        friendly_club.site_id =  current_site
        friendly_club.save()
        return redirect('/cc-report/rnp/friendly-club-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/friendly_club/edit_friendly_club.html', locals())

@ login_required(login_url='/login/')
def balsansad_meeting_listing_rnp_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 6: Details of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    # school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, balsansad_meeting)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/rnp/bal_sansad_metting/bal_sansad_listing.html', locals())

@ login_required(login_url='/login/')
def add_balsansad_meeting_rnp_cc_report(request, task_id):
    heading = "Section 6: Add of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.filter()
    school = School.objects.filter(status=1, id__in=school_id).order_by('name')
    masterlookups_issues_discussion = MasterLookUp.objects.filter(parent__slug = 'issues_discussion')

    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        school_name_id = data.get('school_name')
        school_name = School.objects.get(id=school_name_id)
        no_of_participants = data.get('no_of_participants')
        issues_discussion = data.get('issues_discussion')
        decision_taken = data.get('decision_taken')
        task = Task.objects.get(id=task_id)
        balsansad_meeting = BalSansadMeeting.objects.create(start_date = date_of_registration, school_name=school_name,
        no_of_participants=no_of_participants, decision_taken=decision_taken,
        task=task, site_id = current_site)
        if issues_discussion:
            issues_discussion = MasterLookUp.objects.get(id=issues_discussion)
            balsansad_meeting.issues_discussion = issues_discussion
        balsansad_meeting.save()
        return redirect('/cc-report/rnp/balsansad-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/bal_sansad_metting/add_bal_sansad.html', locals())


@ login_required(login_url='/login/')
def edit_balsansad_meeting_rnp_cc_report(request, balsansad_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 6: Edit of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.get(id=balsansad_id)
    school = School.objects.filter(status=1, id__in=school_id).order_by('name')
    masterlookups_issues_discussion = MasterLookUp.objects.filter(parent__slug = 'issues_discussion')

    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        school_name_id = data.get('school_name')
        school_name = School.objects.get(id=school_name_id)
        no_of_participants = data.get('no_of_participants')
        issues_discussion = data.get('issues_discussion')
        decision_taken = data.get('decision_taken')
        task = Task.objects.get(id=task_id)
        balsansad_meeting.start_date = date_of_registration
        balsansad_meeting.school_name_id = school_name
        balsansad_meeting.no_of_participants = no_of_participants
        balsansad_meeting.decision_taken = decision_taken
        balsansad_meeting.task_id = task
        balsansad_meeting.site_id =  current_site
        if issues_discussion:
            issues_discussion = MasterLookUp.objects.get(id=issues_discussion)
            balsansad_meeting.issues_discussion = issues_discussion
        balsansad_meeting.save()
        return redirect('/cc-report/rnp/balsansad-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/bal_sansad_metting/edit_bal_sansad.html', locals())


@ login_required(login_url='/login/')
def community_activities_listing_rnp_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 7: Details of community engagement activities"
    # village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, activities)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/rnp/community_activities/community_activities_listing.html', locals())


@ login_required(login_url='/login/')
def add_community_activities_rnp_cc_report(request, task_id):
    heading = "Section 7: Add of community engagement activities"
    current_site = request.session.get('site_id')
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.filter(status=1,)
    village =  Village.objects.filter(status=1, id__in=village_id).order_by('name')
    masterlookups_event = MasterLookUp.objects.filter(parent__slug = 'event')
    masterlookups_activity = MasterLookUp.objects.filter(parent__slug = 'activities')

    if request.method == 'POST':
        data = request.POST
        village_name_id = data.get('village_name')
        date_of_registration = data.get('date_of_registration')
        village_name = Village.objects.get(id=village_name_id)
        name_of_event_activity = data.get('name_of_event_activity')
        name_of_event_id = data.get('name_of_event')
        name_of_activity_id = data.get('name_of_activity')
        organized_by = data.get('organized_by')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)

        activities =  CommunityEngagementActivities.objects.create(village_name=village_name, start_date = date_of_registration,
        name_of_event_activity=name_of_event_activity, organized_by=organized_by,
        girls_10_14_year=girls_10_14_year, girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year,
        boys_15_19_year=boys_15_19_year, champions_15_19_year=champions_15_19_year, adult_male=adult_male,
        adult_female=adult_female, teachers=teachers, pri_members=pri_members, services_providers=services_providers,
        sms_members=sms_members, other=other, task=task, site_id = current_site)
        
        if name_of_event_id:
            name_of_event = MasterLookUp.objects.get(id=name_of_event_id)
            activities.event_name = name_of_event

        if name_of_activity_id:
            name_of_activity = MasterLookUp.objects.get(id=name_of_activity_id)
            activities.activity_name = name_of_activity
        activities.save()
        return redirect('/cc-report/rnp/community-activities-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/community_activities/add_community_activities.html', locals())


@ login_required(login_url='/login/')
def edit_community_activities_rnp_cc_report(request, activities_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 7: Edit of community engagement activities"
    current_site = request.session.get('site_id')
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.get(id=activities_id)
    village =  Village.objects.filter(status=1, id__in=village_id).order_by('name')
    masterlookups_event = MasterLookUp.objects.filter(parent__slug = 'event')
    masterlookups_activity = MasterLookUp.objects.filter(parent__slug = 'activities')

    if request.method == 'POST':
        data = request.POST
        village_name_id = data.get('village_name')
        date_of_registration = data.get('date_of_registration')
        village_name = Village.objects.get(id=village_name_id)
        name_of_event_activity = data.get('name_of_event_activity')
        # theme_topic = data.get('theme_topic')
        name_of_event_id = data.get('name_of_event')
        name_of_activity_id = data.get('name_of_activity')

        organized_by = data.get('organized_by')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)

        activities.start_date = date_of_registration
        activities.village_name_id = village_name
        activities.name_of_event_activity = name_of_event_activity
        # activities.theme_topic = theme_topic
        activities.organized_by = organized_by
        activities.boys_10_14_year = boys_10_14_year
        activities.boys_15_19_year = boys_15_19_year
        activities.girls_10_14_year = girls_10_14_year
        activities.girls_15_19_year = girls_15_19_year
        activities.champions_15_19_year = champions_15_19_year
        activities.adult_male = adult_male
        activities.adult_female = adult_female
        activities.teachers = teachers
        activities.pri_members = pri_members
        activities.services_providers = services_providers
        activities.sms_members = sms_members
        activities.other = other
        activities.task_id = task
        activities.site_id =  current_site
        
        if name_of_event_id:
            name_of_event = MasterLookUp.objects.get(id = name_of_event_id)
            activities.event_name = name_of_event

        if name_of_activity_id:
            name_of_activity = MasterLookUp.objects.get(id = name_of_activity_id)
            activities.activity_name = name_of_activity
        activities.save()
        return redirect('/cc-report/rnp/community-activities-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/community_activities/edit_community_activities.html', locals())


@ login_required(login_url='/login/')
def champions_listing_rnp_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 8: Details of exposure visits of adolescent champions"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, champions)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/rnp/champions/champions_listing.html', locals())

@ login_required(login_url='/login/')
def add_champions_rnp_cc_report(request, task_id):
    heading = "Section 8: Add of exposure visits of adolescent champions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.filter(status=1)
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        date_of_visit = data.get('date_of_visit')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        first_inst_visited = data.get('first_inst_visited')
        second_inst_visited = data.get('second_inst_visited')
        third_inst_visited = data.get('third_inst_visited')
        fourth_inst_visited = data.get('fourth_inst_visited')
        task = Task.objects.get(id=task_id)

        champions =  Champions.objects.create(awc_name=awc_name, date_of_visit=date_of_visit, girls_10_14_year=girls_10_14_year,
        girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year, boys_15_19_year=boys_15_19_year,
        first_inst_visited=first_inst_visited,second_inst_visited=second_inst_visited or None,
        third_inst_visited=third_inst_visited or None, fourth_inst_visited=fourth_inst_visited or None, task=task, site_id = current_site)
        champions.save()
        return redirect('/cc-report/rnp/champions-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/champions/add_champions.html', locals())


@ login_required(login_url='/login/')
def edit_champions_rnp_cc_report(request, champions_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 8: Edit of exposure visits of adolescent champions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.get(id=champions_id)
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        date_of_visit = data.get('date_of_visit')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        first_inst_visited = data.get('first_inst_visited')
        second_inst_visited = data.get('second_inst_visited')
        third_inst_visited = data.get('third_inst_visited')
        fourth_inst_visited = data.get('fourth_inst_visited')
        task = Task.objects.get(id=task_id)

        champions.awc_name_id = awc_name       
        champions.date_of_visit = date_of_visit 
        champions.girls_10_14_year = girls_10_14_year       
        champions.girls_15_19_year = girls_15_19_year     
        champions.boys_10_14_year = boys_10_14_year       
        champions.boys_15_19_year = boys_15_19_year       
        champions.first_inst_visited = first_inst_visited
        champions.second_inst_visited= second_inst_visited or None
        champions.third_inst_visited = third_inst_visited or None
        champions.fourth_inst_visited = fourth_inst_visited or None
        champions.task_id = task
        champions.site_id =  current_site       
        champions.save()
        return redirect('/cc-report/rnp/champions-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/champions/edit_champions.html', locals())

@ login_required(login_url='/login/')
def reenrolled_listing_rnp_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 9: Details of adolescent re-enrolled in schools"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, adolescent_reenrolled)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/rnp/re_enrolled/re_enrolled_listing.html', locals())

@ login_required(login_url='/login/')
def add_reenrolled_rnp_cc_report(request, task_id):
    heading = "Section 9: Add of adolescent re-enrolled in schools"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter()
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site).order_by('name')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    # school = School.objects.filter(status=1, id__in = school_id)
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        gender = data.get('gender')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        school_name = data.get('school_name')
        # school_name = School.objects.get(id=school_name_id)
        which_class_enrolled = data.get('which_class_enrolled')
        task = Task.objects.get(id=task_id)
       

        adolescent_reenrolled =  AdolescentRe_enrolled.objects.create(adolescent_name=adolescent_name,
        gender=gender or None, age=age or None, parent_guardian_name=parent_guardian_name, school_name=school_name, which_class_enrolled=which_class_enrolled,
        task=task, site_id = current_site)
        adolescent_reenrolled.save()
        return redirect('/cc-report/rnp/reenrolled-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/re_enrolled/add_re_enrolled.html', locals())


@ login_required(login_url='/login/')
def edit_reenrolled_rnp_cc_report(request, reenrolled_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 9: Edit of adolescent re-enrolled in schools"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.get(id=reenrolled_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site).order_by('name')
    # school = School.objects.filter()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        gender = data.get('gender')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        school_name = data.get('school_name')
        # school_name = School.objects.get(id=school_name_id)
        which_class_enrolled = data.get('which_class_enrolled')
        task = Task.objects.get(id=task_id)
        

        adolescent_reenrolled.adolescent_name_id = adolescent_name
        adolescent_reenrolled.gender = gender or None
        adolescent_reenrolled.age = age or None
        adolescent_reenrolled.parent_guardian_name = parent_guardian_name
        adolescent_reenrolled.school_name = school_name
        adolescent_reenrolled.which_class_enrolled = which_class_enrolled
        adolescent_reenrolled.task_id = task
        adolescent_reenrolled.site_id =  current_site
        adolescent_reenrolled.save()
        return redirect('/cc-report/rnp/reenrolled-listing/'+str(task_id))
    return render(request, 'cc_report/rnp/re_enrolled/edit_re_enrolled.html', locals())


#------------cc-report untrust

@ login_required(login_url='/login/')
def health_sessions_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 1: Details of transaction of sessions on health & nutrition"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, health_sessions)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/health_sessions/health_sessions_listing.html', locals())

@ login_required(login_url='/login/')
def add_health_sessions_untrust_cc_report(request, task_id):
    heading = "Section 1: Add of transaction of sessions on health & nutrition"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    fossil_ah_session_category_obj =  FossilAHSessionCategory.objects.filter(status=1)
  
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_selected_id = data.get('awc_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_ah_session_id = data.get('fossil_ah_session')
        fossil_ah_session_selected_id = data.get('fossil_ah_session_category')
        fossil_ah_session = FossilAHSession.objects.get(id=fossil_ah_session_id)
        date_of_session = data.get('date_of_session')
        age = data.get('age')
        gender = data.get('gender')
        adolescent_obj =  Adolescent.objects.filter(awc__id=adolescent_selected_id, site=current_site)
        fossil_ah_session_obj =  FossilAHSession.objects.filter(fossil_ah_session_category__id = fossil_ah_session_selected_id)
        session_day = data.get('session_day')
        facilitator_name = data.get('facilitator_name')
        designations = data.get('designations')
        task = Task.objects.get(id=task_id)
        if AHSession.objects.filter(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
                                    date_of_session=date_of_session,  status=1).exists():
            exist_error = "Please try again this data already exists!!!"
            return render(request,'cc_report/untrust/health_sessions/add_health_sessions.html', locals())
        else:
            health_sessions = AHSession.objects.create(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
            date_of_session=date_of_session, session_day=session_day,designation_data = designations,
            age=age or None, gender=gender or None, facilitator_name = facilitator_name, task=task, site_id = current_site)
            health_sessions.save()
        return redirect('/cc-report/untrust/health-sessions-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/health_sessions/add_health_sessions.html', locals())


@ login_required(login_url='/login/')
def edit_health_sessions_untrust_cc_report(request, ahsession_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 1: Edit of transaction of sessions on health & nutrition"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.get(id=ahsession_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id=health_sessions.adolescent_name.awc.id, site=current_site)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    fossil_ah_session_obj =  FossilAHSession.objects.filter(status=1, fossil_ah_session_category__id=health_sessions.fossil_ah_session.fossil_ah_session_category.id)
    fossil_ah_session_category_obj =  FossilAHSessionCategory.objects.filter(status=1,)
    
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_ah_session_id = data.get('fossil_ah_session')
        fossil_ah_session = FossilAHSession.objects.get(id=fossil_ah_session_id)
        date_of_session = data.get('date_of_session')
        session_day = data.get('session_day')
        age = data.get('age')
        gender = data.get('gender')
        facilitator_name = data.get('facilitator_name')
        designations = data.get('designations')
        task = Task.objects.get(id=task_id)
        if AHSession.objects.filter(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
                                    date_of_session=date_of_session,  status=1).exclude(id=ahsession_id).exists():
            exist_error = "Please try again this data already exists!!!"
            return render(request, 'cc_report/untrust/health_sessions/edit_health_sessions.html', locals())
        else:
            health_sessions.adolescent_name_id = adolescent_name
            health_sessions.fossil_ah_session_id = fossil_ah_session
            health_sessions.age = age or None
            health_sessions.gender = gender or None
            health_sessions.date_of_session = date_of_session
            health_sessions.session_day = session_day
            health_sessions.designation_data = designations
            health_sessions.facilitator_name = facilitator_name
            health_sessions.task_id = task
            health_sessions.site_id =  current_site
            health_sessions.save()
        return redirect('/cc-report/untrust/health-sessions-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/health_sessions/edit_health_sessions.html', locals())


@ login_required(login_url='/login/')
def girls_ahwd_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 3(a): Details of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    # school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, girls_ahwd)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/girls_ahwd/girls_ahwd_listing.html', locals())


@ login_required(login_url='/login/')
def add_girls_ahwd_untrust_cc_report(request, task_id):
    heading = "Section 3(a): Add of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        tt_10_14_years = data.get('tt_10_14_years')
        tt_15_19_years = data.get('tt_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        girls_ahwd = GirlsAHWD.objects.create(place_of_ahwd=place_of_ahwd, content_type=content_type, object_id=selected_object_id,
        participated_10_14_years=participated_10_14_years, date_of_ahwd=date_of_ahwd, hwc_name=hwc_name,
        participated_15_19_years=participated_15_19_years, bmi_10_14_years=bmi_10_14_years,
        bmi_15_19_years=bmi_15_19_years, hb_10_14_years=hb_10_14_years, hb_15_19_years=hb_15_19_years,
        tt_10_14_years=tt_10_14_years, tt_15_19_years=tt_15_19_years, counselling_10_14_years=counselling_10_14_years,
        counselling_15_19_years=counselling_15_19_years, referral_10_14_years=referral_10_14_years,
        referral_15_19_years=referral_15_19_years, task=task, site_id = current_site)
        girls_ahwd.save()
        return redirect('/cc-report/untrust/girls-ahwd-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/girls_ahwd/add_girls_ahwd.html', locals())


@ login_required(login_url='/login/')
def edit_girls_ahwd_untrust_cc_report(request, girls_ahwd_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 3(a): Edit of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.get(id=girls_ahwd_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        tt_10_14_years = data.get('tt_10_14_years')
        tt_15_19_years = data.get('tt_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        girls_ahwd.place_of_ahwd = place_of_ahwd
        girls_ahwd.content_type = content_type
        girls_ahwd.object_id = selected_object_id
        girls_ahwd.hwc_name = hwc_name
        girls_ahwd.date_of_ahwd = date_of_ahwd
        girls_ahwd.participated_10_14_years = participated_10_14_years
        girls_ahwd.participated_15_19_years = participated_15_19_years
        girls_ahwd.bmi_10_14_years = bmi_10_14_years
        girls_ahwd.bmi_15_19_years = bmi_15_19_years
        girls_ahwd.hb_10_14_years = hb_10_14_years
        girls_ahwd.hb_15_19_years = hb_15_19_years
        girls_ahwd.tt_10_14_years = tt_10_14_years
        girls_ahwd.tt_15_19_years = tt_15_19_years
        girls_ahwd.counselling_10_14_years = counselling_10_14_years
        girls_ahwd.counselling_15_19_years = counselling_15_19_years
        girls_ahwd.referral_10_14_years = referral_10_14_years
        girls_ahwd.referral_15_19_years = referral_15_19_years
        girls_ahwd.task_id = task
        girls_ahwd.site_id =  current_site
        girls_ahwd.save()
        return redirect('/cc-report/untrust/girls-ahwd-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/girls_ahwd/edit_girls_ahwd.html', locals())




@ login_required(login_url='/login/')
def boys_ahwd_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 3(b): Details of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    # school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, boys_ahwd)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/boys_ahwd/boys_ahwd_listing.html', locals())


@ login_required(login_url='/login/')
def add_boys_ahwd_untrust_cc_report(request, task_id):
    heading = "Section 3(b): Add of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        boys_ahwd = BoysAHWD.objects.create(place_of_ahwd=place_of_ahwd, content_type=content_type, object_id=selected_object_id,
        participated_10_14_years=participated_10_14_years, date_of_ahwd=date_of_ahwd, hwc_name=hwc_name,
        participated_15_19_years=participated_15_19_years, bmi_10_14_years=bmi_10_14_years,
        bmi_15_19_years=bmi_15_19_years, hb_10_14_years=hb_10_14_years, hb_15_19_years=hb_15_19_years,
        counselling_10_14_years=counselling_10_14_years,
        counselling_15_19_years=counselling_15_19_years, referral_10_14_years=referral_10_14_years,
        referral_15_19_years=referral_15_19_years, task=task, site_id = current_site)
        boys_ahwd.save()
        return redirect('/cc-report/untrust/boys-ahwd-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/boys_ahwd/add_boys_ahwd.html', locals())


@ login_required(login_url='/login/')
def edit_boys_ahwd_untrust_cc_report(request, boys_ahwd_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 3(b): Edit of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.get(id=boys_ahwd_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        boys_ahwd.place_of_ahwd = place_of_ahwd
        boys_ahwd.content_type = content_type
        boys_ahwd.object_id = selected_object_id
        boys_ahwd.hwc_name = hwc_name
        boys_ahwd.date_of_ahwd = date_of_ahwd
        boys_ahwd.participated_10_14_years = participated_10_14_years
        boys_ahwd.participated_15_19_years = participated_15_19_years
        boys_ahwd.bmi_10_14_years = bmi_10_14_years
        boys_ahwd.bmi_15_19_years = bmi_15_19_years
        boys_ahwd.hb_10_14_years = hb_10_14_years
        boys_ahwd.hb_15_19_years = hb_15_19_years
        boys_ahwd.counselling_10_14_years = counselling_10_14_years
        boys_ahwd.counselling_15_19_years = counselling_15_19_years
        boys_ahwd.referral_10_14_years = referral_10_14_years
        boys_ahwd.referral_15_19_years = referral_15_19_years
        boys_ahwd.task_id = task
        boys_ahwd.site_id =  current_site
        boys_ahwd.save()
        return redirect('/cc-report/untrust/boys-ahwd-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/boys_ahwd/edit_boys_ahwd.html', locals())


@ login_required(login_url='/login/')
def vocation_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 2(a): Details of adolescent linked with vocational training & placement"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, vocation_obj)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/voctional_training/vocation_listing.html', locals())

@ login_required(login_url='/login/')
def add_vocation_untrust_cc_report(request, task_id):
    heading = "Section 2(a): Add of adolescent linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.filter()
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site, age_in_completed_years__gte=18).order_by('name')
    tranining_sub_obj = TrainingSubject.objects.all()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id=training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)
        vocation_obj = AdolescentVocationalTraining.objects.create(adolescent_name=adolescent_name, date_of_registration=date_of_registration, 
        age=age or None, parent_guardian_name=parent_guardian_name, training_subject=training_subject,
        training_providing_by=training_providing_by, duration_days=duration_days, training_complated=training_complated, 
        placement_offered=placement_offered or None, placement_accepted=placement_accepted or None, type_of_employment=type_of_employment or None,
        task=task, site_id = current_site)
        vocation_obj.save()
        return redirect('/cc-report/untrust/vocation-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/voctional_training/add_vocation_training.html', locals())


@ login_required(login_url='/login/')
def edit_vocation_untrust_cc_report(request, vocation_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 2(a): Edit of adolescent linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.get(id=vocation_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site, age_in_completed_years__gte=18).order_by('name')
    tranining_sub_obj = TrainingSubject.objects.all()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id = training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)

        vocation_obj.adolescent_name_id = adolescent_name
        vocation_obj.date_of_registration = date_of_registration
        vocation_obj.age = age or None
        vocation_obj.parent_guardian_name = parent_guardian_name
        vocation_obj.training_subject = training_subject
        vocation_obj.training_providing_by = training_providing_by
        vocation_obj.duration_days = duration_days
        vocation_obj.training_complated = training_complated
        vocation_obj.placement_offered = placement_offered or None
        vocation_obj.placement_accepted = placement_accepted or None
        vocation_obj.type_of_employment = type_of_employment or None
        vocation_obj.task_id = task
        vocation_obj.site_id =  current_site
        vocation_obj.save()
        return redirect('/cc-report/untrust/vocation-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/voctional_training/edit_vocation_training.html', locals())


@ login_required(login_url='/login/')
def parents_vocation_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 2(b): Details of parents linked with vocational training & placement"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    parents_vocation =  ParentVocationalTraining.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, parents_vocation)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/parents_voctional_training/vocation_listing.html', locals())

@ login_required(login_url='/login/')
def add_parents_vocation_untrust_cc_report(request, task_id):
    heading = "Section 2(b): Add of parents linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    parents_vocation =  ParentVocationalTraining.objects.filter()
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site).order_by('name')
    tranining_sub_obj = TrainingSubject.objects.filter(status=1,)

    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_name = data.get('parent_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id = training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)
        parents_vocation = ParentVocationalTraining.objects.create(adolescent_name=adolescent_name, date_of_registration=date_of_registration, 
        age=age or None, parent_name=parent_name, training_subject=training_subject,
        training_providing_by=training_providing_by, duration_days=duration_days, training_complated=training_complated, 
        placement_offered=placement_offered or None, placement_accepted=placement_accepted or None, type_of_employment=type_of_employment or None,
        task=task, site_id = current_site)
        parents_vocation.save()
        return redirect('/cc-report/untrust/parents-vocation-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/parents_voctional_training/add_vocation_training.html', locals())


@ login_required(login_url='/login/')
def edit_parents_vocation_untrust_cc_report(request, parent_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 2(b): Edit of parents linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    parents_vocation =  ParentVocationalTraining.objects.get(id=parent_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site).order_by('name')
    tranining_sub_obj = TrainingSubject.objects.filter(status=1,)

    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_name = data.get('parent_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id = training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)

        parents_vocation.adolescent_name_id = adolescent_name
        parents_vocation.date_of_registration = date_of_registration
        parents_vocation.age = age or None
        parents_vocation.parent_name = parent_name
        parents_vocation.training_subject = training_subject
        parents_vocation.training_providing_by = training_providing_by
        parents_vocation.duration_days = duration_days
        parents_vocation.training_complated = training_complated
        parents_vocation.placement_offered = placement_offered  or None
        parents_vocation.placement_accepted = placement_accepted  or None
        parents_vocation.type_of_employment = type_of_employment  or None
        parents_vocation.task_id = task
        parents_vocation.site_id =  current_site
        parents_vocation.save()
        return redirect('/cc-report/untrust/parents-vocation-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/parents_voctional_training/edit_vocation_training.html', locals())


@ login_required(login_url='/login/')
def adolescents_referred_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 4: Details of adolescents referred"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, adolescents_referred)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/adolescent_referred/adolescent_referred_listing.html', locals())

@ login_required(login_url='/login/')
def add_adolescents_referred_untrust_cc_report(request, task_id):
    heading = "Section 4: Add of adolescents referred"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.filter(status=1)
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_referred_10_14_year = data.get('girls_referred_10_14_year')
        girls_referred_15_19_year = data.get('girls_referred_15_19_year')
        boys_referred_10_14_year = data.get('boys_referred_10_14_year')
        boys_referred_15_19_year = data.get('boys_referred_15_19_year')
        girls_hwc_referred = data.get('girls_hwc_referred')
        girls_hwc_visited = data.get('girls_hwc_visited')
        girls_afhc_referred = data.get('girls_afhc_referred')
        girls_afhc_visited = data.get('girls_afhc_visited')
        girls_dh_referred = data.get('girls_dh_referred')
        girls_dh_visited = data.get('girls_dh_visited')
        boys_hwc_referred = data.get('boys_hwc_referred')
        boys_hwc_visited = data.get('boys_hwc_visited')
        boys_afhc_referred = data.get('boys_afhc_referred')
        boys_afhc_visited = data.get('boys_afhc_visited')
        boys_dh_referred = data.get('boys_dh_referred')
        boys_dh_visited = data.get('boys_dh_visited')
        task = Task.objects.get(id=task_id)
        adolescents_referred = AdolescentsReferred.objects.create(awc_name=awc_name, girls_referred_10_14_year=girls_referred_10_14_year, 
        girls_referred_15_19_year=girls_referred_15_19_year, boys_referred_10_14_year=boys_referred_10_14_year, boys_referred_15_19_year=boys_referred_15_19_year,
        girls_hwc_referred=girls_hwc_referred, girls_hwc_visited=girls_hwc_visited, girls_afhc_referred=girls_afhc_referred, girls_afhc_visited=girls_afhc_visited,
        girls_dh_referred=girls_dh_referred, girls_dh_visited=girls_dh_visited, boys_hwc_referred=boys_hwc_referred, boys_hwc_visited=boys_hwc_visited,
        boys_afhc_referred=boys_afhc_referred, boys_afhc_visited=boys_afhc_visited, 
        boys_dh_referred=boys_dh_referred, boys_dh_visited=boys_dh_visited, task=task, site_id = current_site)
        adolescents_referred.save()
        return redirect('/cc-report/untrust/adolescent-referred-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/adolescent_referred/add_adolescen_referred.html', locals())


@ login_required(login_url='/login/')
def edit_adolescents_referred_untrust_cc_report(request, adolescents_referred_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 4: Edit of adolescents referred"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.get(id=adolescents_referred_id)
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_referred_10_14_year = data.get('girls_referred_10_14_year')
        girls_referred_15_19_year = data.get('girls_referred_15_19_year')
        boys_referred_10_14_year = data.get('boys_referred_10_14_year')
        boys_referred_15_19_year = data.get('boys_referred_15_19_year')
        girls_hwc_referred = data.get('girls_hwc_referred')
        girls_hwc_visited = data.get('girls_hwc_visited')
        girls_afhc_referred = data.get('girls_afhc_referred')
        girls_afhc_visited = data.get('girls_afhc_visited')
        girls_dh_referred = data.get('girls_dh_referred')
        girls_dh_visited = data.get('girls_dh_visited')
        boys_hwc_referred = data.get('boys_hwc_referred')
        boys_hwc_visited = data.get('boys_hwc_visited')
        boys_afhc_referred = data.get('boys_afhc_referred')
        boys_afhc_visited = data.get('boys_afhc_visited')
        boys_dh_referred = data.get('boys_dh_referred')
        boys_dh_visited = data.get('boys_dh_visited')  
        task = Task.objects.get(id=task_id)

        adolescents_referred.awc_name_id = awc_name
        adolescents_referred.girls_referred_10_14_year = girls_referred_10_14_year
        adolescents_referred.girls_referred_15_19_year = girls_referred_15_19_year
        adolescents_referred.boys_referred_10_14_year = boys_referred_10_14_year
        adolescents_referred.boys_referred_15_19_year = boys_referred_15_19_year
        adolescents_referred.girls_hwc_referred = girls_hwc_referred
        adolescents_referred.girls_hwc_visited = girls_hwc_visited
        adolescents_referred.girls_afhc_referred = girls_afhc_referred
        adolescents_referred.girls_afhc_visited = girls_afhc_visited
        adolescents_referred.girls_dh_referred = girls_dh_referred
        adolescents_referred.girls_dh_visited = girls_dh_visited
        adolescents_referred.boys_hwc_referred = boys_hwc_referred
        adolescents_referred.boys_hwc_visited = boys_hwc_visited
        adolescents_referred.boys_afhc_referred = boys_afhc_referred
        adolescents_referred.boys_afhc_visited = boys_afhc_visited
        adolescents_referred.boys_dh_referred = boys_dh_referred
        adolescents_referred.boys_dh_visited = boys_dh_visited
        adolescents_referred.task_id = task
        adolescents_referred.site_id =  current_site
        adolescents_referred.save()
        return redirect('/cc-report/untrust/adolescent-referred-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/adolescent_referred/edit_adolescent_referred.html', locals())


@ login_required(login_url='/login/')
def friendly_club_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 5: Details of Adolescent Friendly Club (AFC)"
    # panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, friendly_club)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/friendly_club/friendly_club_listing.html', locals())

@ login_required(login_url='/login/')
def add_friendly_club_untrust_cc_report(request, task_id):
    heading = "Section 5: Add of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(status=1)
    gramapanchayat = GramaPanchayat.objects.filter(status=1, id__in=panchayat_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        panchayat_name_id = data.get('panchayat_name')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)

        friendly_club = AdolescentFriendlyClub.objects.create(panchayat_name=panchayat_name,
        hsc_name=hsc_name, subject=subject, start_date=date_of_registration, facilitator=facilitator, designation=designation,
        no_of_sahiya=no_of_sahiya, no_of_aww=no_of_aww, pe_girls_10_14_year=pe_girls_10_14_year,
        pe_girls_15_19_year=pe_girls_15_19_year, pe_boys_10_14_year=pe_boys_10_14_year,
        pe_boys_15_19_year=pe_boys_15_19_year, task=task, site_id = current_site)
        friendly_club.save()
        return redirect('/cc-report/untrust/friendly-club-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/friendly_club/add_friendly_club.html', locals())



@ login_required(login_url='/login/')
def edit_friendly_club_untrust_cc_report(request, friendly_club_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 5: Edit of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.get(id=friendly_club_id)
    gramapanchayat = GramaPanchayat.objects.filter(status=1, id__in=panchayat_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        panchayat_name_id = data.get('panchayat_name')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)

        friendly_club.start_date = date_of_registration
        friendly_club.panchayat_name_id = panchayat_name
        friendly_club.hsc_name = hsc_name
        friendly_club.subject = subject
        friendly_club.facilitator = facilitator
        friendly_club.designation = designation
        friendly_club.no_of_sahiya = no_of_sahiya
        friendly_club.no_of_aww = no_of_aww
        friendly_club.pe_girls_10_14_year = pe_girls_10_14_year
        friendly_club.pe_girls_15_19_year = pe_girls_15_19_year
        friendly_club.pe_boys_10_14_year = pe_boys_10_14_year
        friendly_club.pe_boys_15_19_year = pe_boys_15_19_year
        friendly_club.task_id = task
        friendly_club.site_id =  current_site
        friendly_club.save()
        return redirect('/cc-report/untrust/friendly-club-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/friendly_club/edit_friendly_club.html', locals())


@ login_required(login_url='/login/')
def balsansad_meeting_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 6: Details of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    # school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, balsansad_meeting)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/bal_sansad_metting/bal_sansad_listing.html', locals())

@ login_required(login_url='/login/')
def add_balsansad_meeting_untrust_cc_report(request, task_id):
    heading = "Section 6: Add of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.filter()
    school = School.objects.filter(status=1, id__in=school_id).order_by('name')
    masterlookups_issues_discussion = MasterLookUp.objects.filter(parent__slug = 'issues_discussion')

    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        school_name_id = data.get('school_name')
        school_name = School.objects.get(id=school_name_id)
        no_of_participants = data.get('no_of_participants')
        issues_discussion = data.get('issues_discussion')
        decision_taken = data.get('decision_taken')
        task = Task.objects.get(id=task_id)
        balsansad_meeting = BalSansadMeeting.objects.create(start_date = date_of_registration, school_name=school_name,
        no_of_participants=no_of_participants, decision_taken=decision_taken,
        task=task, site_id = current_site)
        if issues_discussion:
            issues_discussion = MasterLookUp.objects.get(id=issues_discussion)
            balsansad_meeting.issues_discussion = issues_discussion
        balsansad_meeting.save()
        return redirect('/cc-report/untrust/balsansad-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/bal_sansad_metting/add_bal_sansad.html', locals())


@ login_required(login_url='/login/')
def edit_balsansad_meeting_untrust_cc_report(request, balsansad_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 6: Edit of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.get(id=balsansad_id)
    school = School.objects.filter(status=1, id__in=school_id).order_by('name')
    masterlookups_issues_discussion = MasterLookUp.objects.filter(parent__slug = 'issues_discussion')

    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        school_name_id = data.get('school_name')
        school_name = School.objects.get(id=school_name_id)
        no_of_participants = data.get('no_of_participants')
        decision_taken = data.get('decision_taken')
        issues_discussion = data.get('issues_discussion')
        task = Task.objects.get(id=task_id)
        balsansad_meeting.start_date = date_of_registration
        balsansad_meeting.school_name_id = school_name
        balsansad_meeting.no_of_participants = no_of_participants
        balsansad_meeting.decision_taken = decision_taken
        balsansad_meeting.task_id = task
        balsansad_meeting.site_id =  current_site
        if issues_discussion:
            issues_discussion = MasterLookUp.objects.get(id=issues_discussion)
            balsansad_meeting.issues_discussion = issues_discussion
        balsansad_meeting.save()
        return redirect('/cc-report/untrust/balsansad-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/bal_sansad_metting/edit_bal_sansad.html', locals())


@ login_required(login_url='/login/')
def community_activities_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 7: Details of community engagement activities"
    # village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, activities)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/community_activities/community_activities_listing.html', locals())


@ login_required(login_url='/login/')
def add_community_activities_untrust_cc_report(request, task_id):
    heading = "Section 7: Add of community engagement activities"
    current_site = request.session.get('site_id')
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.filter(status=1, )
    village =  Village.objects.filter(status=1, id__in=village_id).order_by('name')
    masterlookups_event = MasterLookUp.objects.filter(parent__slug = 'event')
    masterlookups_activity = MasterLookUp.objects.filter(parent__slug = 'activities')

    if request.method == 'POST':
        data = request.POST
        village_name_id = data.get('village_name')
        date_of_registration = data.get('date_of_registration')
        village_name = Village.objects.get(id=village_name_id)
        name_of_event_activity = data.get('name_of_event_activity')
        name_of_event_id = data.get('name_of_event')
        name_of_activity_id = data.get('name_of_activity')
        organized_by = data.get('organized_by')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)

        activities =  CommunityEngagementActivities.objects.create(village_name=village_name, start_date = date_of_registration,
        name_of_event_activity=name_of_event_activity, organized_by=organized_by,
        girls_10_14_year=girls_10_14_year, girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year,
        boys_15_19_year=boys_15_19_year, champions_15_19_year=champions_15_19_year, adult_male=adult_male,
        adult_female=adult_female, teachers=teachers, pri_members=pri_members, services_providers=services_providers,
        sms_members=sms_members, other=other, task=task, site_id = current_site)
        
        if name_of_event_id:
            name_of_event = MasterLookUp.objects.get(id=name_of_event_id)
            activities.event_name = name_of_event

        if name_of_activity_id:
            name_of_activity = MasterLookUp.objects.get(id=name_of_activity_id)
            activities.activity_name = name_of_activity
        activities.save()
        return redirect('/cc-report/untrust/community-activities-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/community_activities/add_community_activities.html', locals())


@ login_required(login_url='/login/')
def edit_community_activities_untrust_cc_report(request, activities_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 7: Edit of community engagement activities"
    current_site = request.session.get('site_id')
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.get(id=activities_id)
    village =  Village.objects.filter(status=1, id__in=village_id).order_by('name')
    masterlookups_event = MasterLookUp.objects.filter(parent__slug = 'event')
    masterlookups_activity = MasterLookUp.objects.filter(parent__slug = 'activities')

    if request.method == 'POST':
        data = request.POST
        village_name_id = data.get('village_name')
        date_of_registration = data.get('date_of_registration')
        village_name = Village.objects.get(id=village_name_id)
        name_of_event_activity = data.get('name_of_event_activity')
        # theme_topic = data.get('theme_topic')
        name_of_event_id = data.get('name_of_event')
        name_of_activity_id = data.get('name_of_activity')

        organized_by = data.get('organized_by')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)

        activities.start_date = date_of_registration
        activities.village_name_id = village_name
        activities.name_of_event_activity = name_of_event_activity
        # activities.theme_topic = theme_topic
        activities.organized_by = organized_by
        activities.boys_10_14_year = boys_10_14_year
        activities.boys_15_19_year = boys_15_19_year
        activities.girls_10_14_year = girls_10_14_year
        activities.girls_15_19_year = girls_15_19_year
        activities.champions_15_19_year = champions_15_19_year
        activities.adult_male = adult_male
        activities.adult_female = adult_female
        activities.teachers = teachers
        activities.pri_members = pri_members
        activities.services_providers = services_providers
        activities.sms_members = sms_members
        activities.other = other
        activities.task_id = task
        activities.site_id =  current_site
        
        if name_of_event_id:
            name_of_event = MasterLookUp.objects.get(id = name_of_event_id)
            activities.event_name = name_of_event

        if name_of_activity_id:
            name_of_activity = MasterLookUp.objects.get(id = name_of_activity_id)
            activities.activity_name = name_of_activity
        activities.save()
        return redirect('/cc-report/untrust/community-activities-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/community_activities/edit_community_activities.html', locals())


@ login_required(login_url='/login/')
def champions_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 8: Details of exposure visits of adolescent champions"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, champions)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/champions/champions_listing.html', locals())

@ login_required(login_url='/login/')
def add_champions_untrust_cc_report(request, task_id):
    heading = "Section 8: Add of exposure visits of adolescent champions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.filter()
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        date_of_visit = data.get('date_of_visit')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        first_inst_visited = data.get('first_inst_visited')
        second_inst_visited = data.get('second_inst_visited')
        third_inst_visited = data.get('third_inst_visited')
        fourth_inst_visited = data.get('fourth_inst_visited')
        task = Task.objects.get(id=task_id)

        champions =  Champions.objects.create(awc_name=awc_name, date_of_visit=date_of_visit, girls_10_14_year=girls_10_14_year,
        girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year, boys_15_19_year=boys_15_19_year,
        first_inst_visited=first_inst_visited,second_inst_visited=second_inst_visited or None,
        third_inst_visited=third_inst_visited or None, fourth_inst_visited=fourth_inst_visited or None,  task=task, site_id = current_site)
        champions.save()
        return redirect('/cc-report/untrust/champions-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/champions/add_champions.html', locals())


@ login_required(login_url='/login/')
def edit_champions_untrust_cc_report(request, champions_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 8: Edit of exposure visits of adolescent champions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.get(id=champions_id)
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        date_of_visit = data.get('date_of_visit')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        first_inst_visited = data.get('first_inst_visited')
        second_inst_visited = data.get('second_inst_visited')
        third_inst_visited = data.get('third_inst_visited')
        fourth_inst_visited = data.get('fourth_inst_visited')
        task = Task.objects.get(id=task_id)

        champions.awc_name_id = awc_name       
        champions.date_of_visit = date_of_visit 
        champions.girls_10_14_year = girls_10_14_year       
        champions.girls_15_19_year = girls_15_19_year     
        champions.boys_10_14_year = boys_10_14_year       
        champions.boys_15_19_year = boys_15_19_year       
        champions.first_inst_visited = first_inst_visited
        champions.second_inst_visited= second_inst_visited or None
        champions.third_inst_visited = third_inst_visited or None
        champions.fourth_inst_visited = fourth_inst_visited or None
        champions.task_id = task
        champions.site_id =  current_site       
        champions.save()
        return redirect('/cc-report/untrust/champions-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/champions/edit_champions.html', locals())

@ login_required(login_url='/login/')
def reenrolled_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 9: Details of adolescent re-enrolled in schools"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, adolescent_reenrolled)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/re_enrolled/re_enrolled_listing.html', locals())

@ login_required(login_url='/login/')
def add_reenrolled_untrust_cc_report(request, task_id):
    heading = "Section 9: Add of adolescent re-enrolled in schools"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter()
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site).order_by('name')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    # school = School.objects.filter(status=1, id__in = school_id)
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        gender = data.get('gender')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        school_name = data.get('school_name')
        # school_name = School.objects.get(id=school_name_id)
        which_class_enrolled = data.get('which_class_enrolled')
        task = Task.objects.get(id=task_id)

        adolescent_reenrolled =  AdolescentRe_enrolled.objects.create(adolescent_name=adolescent_name,
        gender=gender or None, age=age or None, parent_guardian_name=parent_guardian_name, school_name=school_name, which_class_enrolled=which_class_enrolled,
        task=task, site_id = current_site)
        adolescent_reenrolled.save()
        return redirect('/cc-report/untrust/reenrolled-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/re_enrolled/add_re_enrolled.html', locals())


@ login_required(login_url='/login/')
def edit_reenrolled_untrust_cc_report(request, reenrolled_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 9: Edit of adolescent re-enrolled in schools"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.get(id=reenrolled_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site).order_by('name')
    # school = School.objects.filter()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        gender = data.get('gender')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        school_name = data.get('school_name')
        # school_name = School.objects.get(id=school_name_id)
        which_class_enrolled = data.get('which_class_enrolled')
        task = Task.objects.get(id=task_id)

        adolescent_reenrolled.adolescent_name_id = adolescent_name
        adolescent_reenrolled.gender = gender or None
        adolescent_reenrolled.age = age or None
        adolescent_reenrolled.parent_guardian_name = parent_guardian_name
        adolescent_reenrolled.school_name = school_name
        adolescent_reenrolled.which_class_enrolled = which_class_enrolled
        adolescent_reenrolled.task_id = task
        adolescent_reenrolled.site_id =  current_site
        adolescent_reenrolled.save()
        return redirect('/cc-report/untrust/reenrolled-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/re_enrolled/edit_re_enrolled.html', locals())

@ login_required(login_url='/login/')
def vlcpc_meeting_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 10: Details of VLCPC meetings"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vlcpc_metting =  VLCPCMetting.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, vlcpc_metting)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/vlcpc_meetings/vlcpc_meeting_listing.html', locals())

@ login_required(login_url='/login/')
def add_vlcpc_meeting_untrust_cc_report(request, task_id):
    heading = "Section 10: Add of VLCPC meetings"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vlcpc_metting =  VLCPCMetting.objects.filter()
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        date_of_meeting = data.get('date_of_meeting')
        issues_discussed = data.get('issues_discussed')
        decision_taken = data.get('decision_taken')
        no_of_participants_planned = data.get('no_of_participants_planned')
        no_of_participants_attended = data.get('no_of_participants_attended')
        task = Task.objects.get(id=task_id)

        vlcpc_metting = VLCPCMetting.objects.create(awc_name=awc_name, date_of_meeting=date_of_meeting,
        issues_discussed=issues_discussed, decision_taken=decision_taken, no_of_participants_planned=no_of_participants_planned,
        no_of_participants_attended=no_of_participants_attended, task=task, site_id = current_site)
        vlcpc_metting.save()
        return redirect('/cc-report/untrust/vlcpc-meeting-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/vlcpc_meetings/add_vlcpc_meeting.html', locals())


@ login_required(login_url='/login/')
def edit_vlcpc_meeting_untrust_cc_report(request, vlcpc_metting, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 10: Edit of VLCPC meetings"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vlcpc_metting =  VLCPCMetting.objects.get(id=vlcpc_metting)
    awc =  AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        date_of_meeting = data.get('date_of_meeting')
        issues_discussed = data.get('issues_discussed')
        decision_taken = data.get('decision_taken')
        no_of_participants_planned = data.get('no_of_participants_planned')
        no_of_participants_attended = data.get('no_of_participants_attended')
        task = Task.objects.get(id=task_id)

        vlcpc_metting.awc_name_id = awc_name
        vlcpc_metting.date_of_meeting = date_of_meeting
        vlcpc_metting.issues_discussed = issues_discussed
        vlcpc_metting.decision_taken = decision_taken
        vlcpc_metting.no_of_participants_planned = no_of_participants_planned
        vlcpc_metting.no_of_participants_attended = no_of_participants_attended
        vlcpc_metting.task_id = task
        vlcpc_metting.site_id =  current_site
        vlcpc_metting.save()
        return redirect('/cc-report/untrust/vlcpc-meeting-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/vlcpc_meetings/edit_vlcpc_meeting.html', locals())

@ login_required(login_url='/login/')
def dcpu_bcpu_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 11: Details of DCPU/BCPU engagement at community and institutional level"
    # block_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__block__id')
    dcpu_bcpu = DCPU_BCPU.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, dcpu_bcpu)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/dcpu_bcpu/dcpu_bcpu_listing.html', locals())

@ login_required(login_url='/login/')
def add_dcpu_bcpu_untrust_cc_report(request, task_id):
    heading = "Section 11: Add of DCPU/BCPU engagement at community and institutional level"
    current_site = request.session.get('site_id')
    block_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__block__id')
    dcpu_bcpu = DCPU_BCPU.objects.filter(status=1)
    block_obj = Block.objects.filter(status=1, id__in=block_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        block_name_id = data.get('block_name')
        block_name = Block.objects.get(id=block_name_id)
        name_of_institution = data.get('name_of_institution')
        date_of_visit = data.get('date_of_visit')
        name_of_lead = data.get('name_of_lead')
        designation = data.get('designation')
        issues_discussed = data.get('issues_discussed')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)
        
        dcpu_bcpu = DCPU_BCPU.objects.create(block_name=block_name, name_of_institution=name_of_institution,
        date_of_visit=date_of_visit, name_of_lead=name_of_lead, designation=designation, issues_discussed=issues_discussed,
        girls_10_14_year=girls_10_14_year, girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year,
        boys_15_19_year=boys_15_19_year, champions_15_19_year=champions_15_19_year,
        adult_male=adult_male, adult_female=adult_female, teachers=teachers, pri_members=pri_members, 
        services_providers=services_providers, sms_members=sms_members, other=other,
        task=task, site_id = current_site )
        dcpu_bcpu.save()
        return redirect('/cc-report/untrust/dcpu-bcpu-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/dcpu_bcpu/add_dcpu_bcpu.html', locals())



@ login_required(login_url='/login/')
def edit_dcpu_bcpu_untrust_cc_report(request, dcpu_bcpu_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 11: Edit of DCPU/BCPU engagement at community and institutional level"
    current_site = request.session.get('site_id')
    block_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__block__id')
    dcpu_bcpu = DCPU_BCPU.objects.get(id=dcpu_bcpu_id)
    block_obj = Block.objects.filter(status=1, id__in=block_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        block_name_id = data.get('block_name')
        block_name = Block.objects.get(id=block_name_id)
        name_of_institution = data.get('name_of_institution')
        date_of_visit = data.get('date_of_visit')
        name_of_lead = data.get('name_of_lead')
        designation = data.get('designation')
        issues_discussed = data.get('issues_discussed')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)


        dcpu_bcpu.block_name_id = block_name
        dcpu_bcpu.name_of_institution = name_of_institution 
        dcpu_bcpu.date_of_visit = date_of_visit 
        dcpu_bcpu.name_of_lead = name_of_lead 
        dcpu_bcpu.designation = designation 
        dcpu_bcpu.issues_discussed = issues_discussed 
        dcpu_bcpu.girls_10_14_year = girls_10_14_year 
        dcpu_bcpu.girls_15_19_year = girls_15_19_year 
        dcpu_bcpu.boys_10_14_year = boys_10_14_year 
        dcpu_bcpu.boys_15_19_year = boys_15_19_year 
        dcpu_bcpu.champions_15_19_year = champions_15_19_year 
        dcpu_bcpu.adult_male = adult_male 
        dcpu_bcpu.adult_female = adult_female 
        dcpu_bcpu.teachers = teachers 
        dcpu_bcpu.pri_members = pri_members 
        dcpu_bcpu.services_providers = services_providers 
        dcpu_bcpu.sms_members = sms_members 
        dcpu_bcpu.other = other 
        dcpu_bcpu.task_id = task 
        dcpu_bcpu.site_id =  current_site 
        dcpu_bcpu.save()
        return redirect('/cc-report/untrust/dcpu-bcpu-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/dcpu_bcpu/edit_dcpu_bcpu.html', locals())



@ login_required(login_url='/login/')
def educational_enrichment_listing_untrust_cc_report(request, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 12: Details of educational enrichment support provided"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    education_enrichment =  EducatinalEnrichmentSupportProvided.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, education_enrichment)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'cc_report/untrust/educational_enrichment/educational_enrichment_listing.html', locals())



@ login_required(login_url='/login/')
def add_educational_enrichment_untrust_cc_report(request, task_id):
    heading = "Section 12: Add of educational enrichment support provided"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    education_enrichment =  EducatinalEnrichmentSupportProvided.objects.filter(status=1, )
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site).order_by('name')
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        parent_guardian_name = data.get('parent_guardian_name')
        enrolment_date = data.get('enrolment_date')
        standard = data.get('standard')
        duration_of_coaching_support = data.get('duration_of_coaching_support')
        task = Task.objects.get(id=task_id)
        education_enrichment =  EducatinalEnrichmentSupportProvided.objects.create(adolescent_name=adolescent_name,
        parent_guardian_name=parent_guardian_name, standard=standard, enrolment_date=enrolment_date,
        duration_of_coaching_support=duration_of_coaching_support, task=task, site_id = current_site)
        education_enrichment.save()
        return redirect('/cc-report/untrust/educational-enrichment-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/educational_enrichment/add_educational_enrichment.html', locals())


@ login_required(login_url='/login/')
def edit_educational_enrichment_untrust_cc_report(request, educational_id, task_id):
    user = get_user(request)
    user_role = str(user.groups.last())
    task_obj = Task.objects.get(status=1, id=task_id)
    heading = "Section 12: edit of educational enrichment support provided"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    education_enrichment =  EducatinalEnrichmentSupportProvided.objects.get(id=educational_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site).order_by('name')
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        parent_guardian_name = data.get('parent_guardian_name')
        enrolment_date = data.get('enrolment_date')
        standard = data.get('standard')
        duration_of_coaching_support = data.get('duration_of_coaching_support')
        task = Task.objects.get(id=task_id)

        education_enrichment.adolescent_name_id = adolescent_name
        education_enrichment.parent_guardian_name = parent_guardian_name
        education_enrichment.enrolment_date = enrolment_date
        education_enrichment.standard = standard
        education_enrichment.duration_of_coaching_support = duration_of_coaching_support
        education_enrichment.task_id = task
        education_enrichment.site_id =  current_site
        education_enrichment.save()
        return redirect('/cc-report/untrust/educational-enrichment-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/educational_enrichment/edit_educational_enrichment.html', locals())


#--- ---------po-report-fossil--------------


@ login_required(login_url='/login/')
def health_sessions_listing_fossil_po_report(request, task_id):
    heading = "Section 1: Details of transaction of sessions on health & nutrition"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, health_sessions)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/health_sessions/health_sessions_listing.html', locals())

@ login_required(login_url='/login/')
def add_health_sessions_fossil_po_report(request, task_id):
    heading = "Section 1: Add of transaction of sessions on health & nutrition"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, site=current_site)
    fossil_ah_session_category_obj =  FossilAHSessionCategory.objects.filter(status=1).exclude(session_category='Engaging Adolescents for Gender Equality Manual')
  
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_selected_id = data.get('awc_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_ah_session_id = data.get('fossil_ah_session')
        fossil_ah_session_selected_id = data.get('fossil_ah_session_category')
        fossil_ah_session = FossilAHSession.objects.get(id=fossil_ah_session_id)
        date_of_session = data.get('date_of_session')
        adolescent_obj =  Adolescent.objects.filter(awc__id=adolescent_selected_id, site=current_site)
        fossil_ah_session_obj =  FossilAHSession.objects.filter(fossil_ah_session_category__id = fossil_ah_session_selected_id)
        session_day = data.get('session_day')
        age = data.get('age')
        gender = data.get('gender')
        facilitator_name = data.get('facilitator_name')
        designations = data.get('designations')
        task = Task.objects.get(id=task_id)
        if AHSession.objects.filter(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
                                    date_of_session=date_of_session,  status=1).exists():
            exist_error = "Please try again this data already exists!!!"
            return render(request,'po_report/fossil/health_sessions/add_health_sessions.html', locals())
        else:
            health_sessions = AHSession.objects.create(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
            date_of_session=date_of_session, session_day=session_day,designation_data = designations,
            age=age or None, gender=gender or None, facilitator_name = facilitator_name, task=task, site_id = current_site)
            health_sessions.save()
        return redirect('/po-report/fossil/health-sessions-listing/'+str(task_id))
    return render(request, 'po_report/fossil/health_sessions/add_health_sessions.html', locals())


@ login_required(login_url='/login/')
def edit_health_sessions_fossil_po_report(request, ahsession_id, task_id):
    heading = "Section 1: Edit of transaction of sessions on health & nutrition"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.get(id=ahsession_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id=health_sessions.adolescent_name.awc.id, site=current_site)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    fossil_ah_session_obj =  FossilAHSession.objects.filter(status=1, fossil_ah_session_category__id=health_sessions.fossil_ah_session.fossil_ah_session_category.id)
    fossil_ah_session_category_obj =  FossilAHSessionCategory.objects.filter(status=1,).exclude(session_category='Engaging Adolescents for Gender Equality Manual')
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_ah_session_id = data.get('fossil_ah_session')
        fossil_ah_session = FossilAHSession.objects.get(id=fossil_ah_session_id)
        date_of_session = data.get('date_of_session')
        session_day = data.get('session_day')
        age = data.get('age')
        gender = data.get('gender')
        facilitator_name = data.get('facilitator_name')
        designations = data.get('designations')
        task = Task.objects.get(id=task_id)
        if AHSession.objects.filter(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
                                    date_of_session=date_of_session,  status=1).exclude(id=ahsession_id).exists():
            exist_error = "Please try again this data already exists!!!"
            return render(request, 'po_report/fossil/health_sessions/edit_health_sessions.html', locals())
        else:
            health_sessions.adolescent_name_id = adolescent_name
            health_sessions.fossil_ah_session_id = fossil_ah_session
            health_sessions.date_of_session = date_of_session
            health_sessions.age = age or None
            health_sessions.gender = gender or None
            health_sessions.session_day = session_day
            health_sessions.designation_data = designations
            health_sessions.facilitator_name = facilitator_name
            health_sessions.task_id = task
            health_sessions.site_id =  current_site
            health_sessions.save()
        return redirect('/po-report/fossil/health-sessions-listing/'+str(task_id))
    return render(request, 'po_report/fossil/health_sessions/edit_health_sessions.html', locals())




@ login_required(login_url='/login/')
def digital_literacy_listing_fossil_po_report(request, task_id):
    heading = "Section 2: Details of transaction of digital literacy sessions"
    awc_id = CC_AWC_DL.objects.filter(status=1, user=request.user).values_list('awc__id')
    digital_literacy = DLSession.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, digital_literacy)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/digital_literacy/digital_literacy_listing.html', locals())


@ login_required(login_url='/login/')
def add_digital_literacy_fossil_po_report(request, task_id):
    heading = "Section 2: Add of transaction of digital literacy sessions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_DL.objects.filter(status=1, user=request.user).values_list('awc__id')
    digital_literacy = DLSession.objects.filter(status=1)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    fossil_dl_session_category_obj =  FossilDLSessionConfig.objects.filter(status=1,)
    
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_selected_id = data.get('awc_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_dl_session_config_id = data.get('fossil_dl_session_config')
        fossil_dl_session_config = FossilDLSessionConfig.objects.get(id=fossil_dl_session_config_id)
        session_name = data.get('session_name')
        age = data.get('age')
        gender = data.get('gender')
        facilitator_name = data.get('facilitator_name')
        date_of_session = data.get('date_of_session')
        adolescent_obj =  Adolescent.objects.filter(awc__id=adolescent_selected_id, site=current_site)
        session_day = data.get('session_day')
        task = Task.objects.get(id=task_id)
        if DLSession.objects.filter(adolescent_name=adolescent_name, fossil_dl_session_config=fossil_dl_session_config,
                                    date_of_session=date_of_session,  status=1).exists():
            exist_error = "This data already exist!!!"
            return render(request, 'po_report/fossil/digital_literacy/add_digital_literacy.html', locals())
        else:
            digital_literacy = DLSession.objects.create(adolescent_name=adolescent_name, fossil_dl_session_config=fossil_dl_session_config,
            date_of_session=date_of_session, session_name=session_name, age=age or None, gender=gender or None, facilitator_name=facilitator_name, 
            session_day=session_day, task=task, site_id = current_site)
            digital_literacy.save()
        return redirect('/po-report/fossil/digital-literacy-listing/'+str(task_id))
    return render(request, 'po_report/fossil/digital_literacy/add_digital_literacy.html', locals())



@ login_required(login_url='/login/')
def edit_digital_literacy_fossil_po_report(request, dlsession_id, task_id):
    heading = "Section 2: Edit of transaction of digital literacy sessions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_DL.objects.filter(status=1, user=request.user).values_list('awc__id')
    digital_literacy = DLSession.objects.get(id=dlsession_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id=digital_literacy.adolescent_name.awc.id, site=current_site)
    fossil_dl_session_category_obj =  FossilDLSessionConfig.objects.filter(status=1,)

    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_dl_session_config_id = data.get('fossil_dl_session_config')
        fossil_dl_session_config = FossilDLSessionConfig.objects.get(id=fossil_dl_session_config_id)
        session_name = data.get('session_name')
        date_of_session = data.get('date_of_session')
        session_day = data.get('session_day')
        age = data.get('age')
        gender = data.get('gender')
        facilitator_name = data.get('facilitator_name')
        task = Task.objects.get(id=task_id)
        if DLSession.objects.filter(adolescent_name=adolescent_name, fossil_dl_session_config=fossil_dl_session_config,
                                    date_of_session=date_of_session,  status=1).exclude(id=dlsession_id).exists():
            exist_error = "This data already exist!!!"
            return render(request, 'po_report/fossil/digital_literacy/edit_digital_literacy.html', locals())
        else:
            digital_literacy.adolescent_name_id = adolescent_name
            digital_literacy.fossil_dl_session_config_id = fossil_dl_session_config
            digital_literacy.date_of_session = date_of_session
            digital_literacy.age = age
            digital_literacy.gender = gender
            digital_literacy.facilitator_name = facilitator_name
            digital_literacy.session_day = session_day
            digital_literacy.session_name = session_name
            digital_literacy.task_id = task
            digital_literacy.site_id =  current_site
            digital_literacy.save()
        return redirect('/po-report/fossil/digital-literacy-listing/'+str(task_id))
    return render(request, 'po_report/fossil/digital_literacy/edit_digital_literacy.html', locals())


@ login_required(login_url='/login/')
def girls_ahwd_listing_fossil_po_report(request, task_id):
    heading = "Section 4(a): Details of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, girls_ahwd)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/girls_ahwd/girls_ahwd_listing.html', locals())


@ login_required(login_url='/login/')
def add_girls_ahwd_fossil_po_report(request, task_id):
    heading = "Section 4(a): Add of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    school_obj = School.objects.filter(status=1, id__in=school_id)
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        tt_10_14_years = data.get('tt_10_14_years')
        tt_15_19_years = data.get('tt_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        girls_ahwd = GirlsAHWD.objects.create(place_of_ahwd=place_of_ahwd, content_type=content_type, object_id=selected_object_id,
        participated_10_14_years=participated_10_14_years, date_of_ahwd=date_of_ahwd, hwc_name=hwc_name,
        participated_15_19_years=participated_15_19_years, bmi_10_14_years=bmi_10_14_years,
        bmi_15_19_years=bmi_15_19_years, hb_10_14_years=hb_10_14_years, hb_15_19_years=hb_15_19_years,
        tt_10_14_years=tt_10_14_years, tt_15_19_years=tt_15_19_years, counselling_10_14_years=counselling_10_14_years,
        counselling_15_19_years=counselling_15_19_years, referral_10_14_years=referral_10_14_years,
        referral_15_19_years=referral_15_19_years, task=task, site_id = current_site)
        girls_ahwd.save()
        return redirect('/po-report/fossil/girls-ahwd-listing/'+str(task_id))
    return render(request, 'po_report/fossil/girls_ahwd/add_girls_ahwd.html', locals())


@ login_required(login_url='/login/')
def edit_girls_ahwd_fossil_po_report(request, girls_ahwd_id, task_id):
    heading = "Section 4(a): Edit of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.get(id=girls_ahwd_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    school_obj = School.objects.filter(status=1, id__in=school_id)
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        tt_10_14_years = data.get('tt_10_14_years')
        tt_15_19_years = data.get('tt_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        girls_ahwd.place_of_ahwd = place_of_ahwd
        girls_ahwd.content_type = content_type
        girls_ahwd.object_id = selected_object_id
        girls_ahwd.hwc_name = hwc_name
        girls_ahwd.date_of_ahwd = date_of_ahwd
        girls_ahwd.participated_10_14_years = participated_10_14_years
        girls_ahwd.participated_15_19_years = participated_15_19_years
        girls_ahwd.bmi_10_14_years = bmi_10_14_years
        girls_ahwd.bmi_15_19_years = bmi_15_19_years
        girls_ahwd.hb_10_14_years = hb_10_14_years
        girls_ahwd.hb_15_19_years = hb_15_19_years
        girls_ahwd.tt_10_14_years = tt_10_14_years
        girls_ahwd.tt_15_19_years = tt_15_19_years
        girls_ahwd.counselling_10_14_years = counselling_10_14_years
        girls_ahwd.counselling_15_19_years = counselling_15_19_years
        girls_ahwd.referral_10_14_years = referral_10_14_years
        girls_ahwd.referral_15_19_years = referral_15_19_years
        girls_ahwd.task_id = task
        girls_ahwd.site_id =  current_site
        girls_ahwd.save()
        return redirect('/po-report/fossil/girls-ahwd-listing/'+str(task_id))
    return render(request, 'po_report/fossil/girls_ahwd/edit_girls_ahwd.html', locals())




@ login_required(login_url='/login/')
def boys_ahwd_listing_fossil_po_report(request, task_id):
    heading = "Section 4(b): Details of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, boys_ahwd)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/boys_ahwd/boys_ahwd_listing.html', locals())


@ login_required(login_url='/login/')
def add_boys_ahwd_fossil_po_report(request, task_id):
    heading = "Section 4(b): Add of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    school_obj = School.objects.filter(status=1, id__in=school_id)
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        boys_ahwd = BoysAHWD.objects.create(place_of_ahwd=place_of_ahwd, content_type=content_type, object_id=selected_object_id,
        participated_10_14_years=participated_10_14_years, date_of_ahwd=date_of_ahwd, hwc_name=hwc_name,
        participated_15_19_years=participated_15_19_years, bmi_10_14_years=bmi_10_14_years,
        bmi_15_19_years=bmi_15_19_years, hb_10_14_years=hb_10_14_years, hb_15_19_years=hb_15_19_years,
        counselling_10_14_years=counselling_10_14_years,
        counselling_15_19_years=counselling_15_19_years, referral_10_14_years=referral_10_14_years,
        referral_15_19_years=referral_15_19_years, task=task, site_id = current_site)
        boys_ahwd.save()
        return redirect('/po-report/fossil/boys-ahwd-listing/'+str(task_id))
    return render(request, 'po_report/fossil/boys_ahwd/add_boys_ahwd.html', locals())


@ login_required(login_url='/login/')
def edit_boys_ahwd_fossil_po_report(request, boys_ahwd_id, task_id):
    heading = "Section 4(b): Edit of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.get(id=boys_ahwd_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    school_obj = School.objects.filter(status=1, id__in=school_id)
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        boys_ahwd.place_of_ahwd = place_of_ahwd
        boys_ahwd.content_type = content_type
        boys_ahwd.object_id = selected_object_id
        boys_ahwd.hwc_name = hwc_name
        boys_ahwd.date_of_ahwd = date_of_ahwd
        boys_ahwd.participated_10_14_years = participated_10_14_years
        boys_ahwd.participated_15_19_years = participated_15_19_years
        boys_ahwd.bmi_10_14_years = bmi_10_14_years
        boys_ahwd.bmi_15_19_years = bmi_15_19_years
        boys_ahwd.hb_10_14_years = hb_10_14_years
        boys_ahwd.hb_15_19_years = hb_15_19_years
        boys_ahwd.counselling_10_14_years = counselling_10_14_years
        boys_ahwd.counselling_15_19_years = counselling_15_19_years
        boys_ahwd.referral_10_14_years = referral_10_14_years
        boys_ahwd.referral_15_19_years = referral_15_19_years
        boys_ahwd.task_id = task
        boys_ahwd.site_id =  current_site
        boys_ahwd.save()
        return redirect('/po-report/fossil/boys-ahwd-listing/'+str(task_id))
    return render(request, 'po_report/fossil/boys_ahwd/edit_boys_ahwd.html', locals())



@ login_required(login_url='/login/')
def vocation_listing_fossil_po_report(request, task_id):
    heading = "Section 3: Details of adolescent linked with vocational training & placement"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, vocation_obj)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/voctional_training/vocation_listing.html', locals())

@ login_required(login_url='/login/')
def add_vocation_fossil_po_report(request, task_id):
    heading = "Section 3: Add of adolescent linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.filter()
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    tranining_sub_obj = TrainingSubject.objects.all()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id=training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)
        vocation_obj = AdolescentVocationalTraining.objects.create(adolescent_name=adolescent_name, date_of_registration=date_of_registration, 
        age=age or None, parent_guardian_name=parent_guardian_name, training_subject=training_subject,
        training_providing_by=training_providing_by, duration_days=duration_days, training_complated=training_complated, 
        placement_offered=placement_offered or None, placement_accepted=placement_accepted or None, type_of_employment=type_of_employment or None,
        task=task, site_id = current_site)
        vocation_obj.save()
        return redirect('/po-report/fossil/vocation-listing/'+str(task_id))
    return render(request, 'po_report/fossil/voctional_training/add_vocation_training.html', locals())


@ login_required(login_url='/login/')
def edit_vocation_fossil_po_report(request, vocation_id, task_id):
    heading = "Section 3: Edit of adolescent linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.get(id=vocation_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    tranining_sub_obj = TrainingSubject.objects.all()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id = training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)

        vocation_obj.adolescent_name_id = adolescent_name
        vocation_obj.date_of_registration = date_of_registration
        vocation_obj.age = age or None
        vocation_obj.parent_guardian_name = parent_guardian_name
        vocation_obj.training_subject = training_subject
        vocation_obj.training_providing_by = training_providing_by
        vocation_obj.duration_days = duration_days
        vocation_obj.training_complated = training_complated
        vocation_obj.placement_offered = placement_offered or None
        vocation_obj.placement_accepted = placement_accepted or None
        vocation_obj.type_of_employment = type_of_employment or None
        vocation_obj.task_id = task
        vocation_obj.site_id =  current_site
        vocation_obj.save()
        return redirect('/po-report/fossil/vocation-listing/'+str(task_id))
    return render(request, 'po_report/fossil/voctional_training/edit_vocation_training.html', locals())



@ login_required(login_url='/login/')
def adolescents_referred_listing_fossil_po_report(request, task_id):
    heading = "Section 5: Details of adolescents referred"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.filter(status=1, awc_name__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, adolescents_referred)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/adolescent_referred/adolescent_referred_listing.html', locals())

@ login_required(login_url='/login/')
def add_adolescents_referred_fossil_po_report(request, task_id):
    heading = "Section 5: Add of adolescents referred"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.filter()
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_referred_10_14_year = data.get('girls_referred_10_14_year')
        girls_referred_15_19_year = data.get('girls_referred_15_19_year')
        boys_referred_10_14_year = data.get('boys_referred_10_14_year')
        boys_referred_15_19_year = data.get('boys_referred_15_19_year')
        girls_hwc_referred = data.get('girls_hwc_referred')
        girls_hwc_visited = data.get('girls_hwc_visited')
        girls_afhc_referred = data.get('girls_afhc_referred')
        girls_afhc_visited = data.get('girls_afhc_visited')
        girls_dh_referred = data.get('girls_dh_referred')
        girls_dh_visited = data.get('girls_dh_visited')
        boys_hwc_referred = data.get('boys_hwc_referred')
        boys_hwc_visited = data.get('boys_hwc_visited')
        boys_afhc_referred = data.get('boys_afhc_referred')
        boys_afhc_visited = data.get('boys_afhc_visited')
        boys_dh_referred = data.get('boys_dh_referred')
        boys_dh_visited = data.get('boys_dh_visited')
        
        task = Task.objects.get(id=task_id)
        adolescents_referred = AdolescentsReferred.objects.create(awc_name=awc_name, girls_referred_10_14_year=girls_referred_10_14_year, 
        girls_referred_15_19_year=girls_referred_15_19_year, boys_referred_10_14_year=boys_referred_10_14_year, boys_referred_15_19_year=boys_referred_15_19_year,
        girls_hwc_referred=girls_hwc_referred, girls_hwc_visited=girls_hwc_visited, girls_afhc_referred=girls_afhc_referred, girls_afhc_visited=girls_afhc_visited,
        girls_dh_referred=girls_dh_referred, girls_dh_visited=girls_dh_visited, boys_hwc_referred=boys_hwc_referred, boys_hwc_visited=boys_hwc_visited,
        boys_afhc_referred=boys_afhc_referred, boys_afhc_visited=boys_afhc_visited, 
        boys_dh_referred=boys_dh_referred, boys_dh_visited=boys_dh_visited, task=task, site_id = current_site)
        adolescents_referred.save()
        return redirect('/po-report/fossil/adolescent-referred-listing/'+str(task_id))
    return render(request, 'po_report/fossil/adolescent_referred/add_adolescen_referred.html', locals())


@ login_required(login_url='/login/')
def edit_adolescents_referred_fossil_po_report(request, adolescents_referred_id, task_id):
    heading = "Section 5: Edit of adolescents referred"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.get(id=adolescents_referred_id)
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_referred_10_14_year = data.get('girls_referred_10_14_year')
        girls_referred_15_19_year = data.get('girls_referred_15_19_year')
        boys_referred_10_14_year = data.get('boys_referred_10_14_year')
        boys_referred_15_19_year = data.get('boys_referred_15_19_year')
        girls_hwc_referred = data.get('girls_hwc_referred')
        girls_hwc_visited = data.get('girls_hwc_visited')
        girls_afhc_referred = data.get('girls_afhc_referred')
        girls_afhc_visited = data.get('girls_afhc_visited')
        girls_dh_referred = data.get('girls_dh_referred')
        girls_dh_visited = data.get('girls_dh_visited')
        boys_hwc_referred = data.get('boys_hwc_referred')
        boys_hwc_visited = data.get('boys_hwc_visited')
        boys_afhc_referred = data.get('boys_afhc_referred')
        boys_afhc_visited = data.get('boys_afhc_visited')
        boys_dh_referred = data.get('boys_dh_referred')
        boys_dh_visited = data.get('boys_dh_visited')  
        task = Task.objects.get(id=task_id)

        adolescents_referred.awc_name_id = awc_name
        adolescents_referred.girls_referred_10_14_year = girls_referred_10_14_year
        adolescents_referred.girls_referred_15_19_year = girls_referred_15_19_year
        adolescents_referred.boys_referred_10_14_year = boys_referred_10_14_year
        adolescents_referred.boys_referred_15_19_year = boys_referred_15_19_year
        adolescents_referred.girls_hwc_referred = girls_hwc_referred
        adolescents_referred.girls_hwc_visited = girls_hwc_visited
        adolescents_referred.girls_afhc_referred = girls_afhc_referred
        adolescents_referred.girls_afhc_visited = girls_afhc_visited
        adolescents_referred.girls_dh_referred = girls_dh_referred
        adolescents_referred.girls_dh_visited = girls_dh_visited
        adolescents_referred.boys_hwc_referred = boys_hwc_referred
        adolescents_referred.boys_hwc_visited = boys_hwc_visited
        adolescents_referred.boys_afhc_referred = boys_afhc_referred
        adolescents_referred.boys_afhc_visited = boys_afhc_visited
        adolescents_referred.boys_dh_referred = boys_dh_referred
        adolescents_referred.boys_dh_visited = boys_dh_visited
        adolescents_referred.task_id = task
        adolescents_referred.site_id =  current_site
        adolescents_referred.save()
        return redirect('/po-report/fossil/adolescent-referred-listing/'+str(task_id))
    return render(request, 'po_report/fossil/adolescent_referred/edit_adolescent_referred.html', locals())


@ login_required(login_url='/login/')
def friendly_club_listing_fossil_po_report(request, task_id):
    heading = "Section 6: Details of Adolescent Friendly Club (AFC)"
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(status=1, panchayat_name__id__in=panchayat_id, task__id = task_id)
    data = pagination_function(request, friendly_club)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/friendly_club/friendly_club_listing.html', locals())

@ login_required(login_url='/login/')
def add_friendly_club_fossil_po_report(request, task_id):
    heading = "Section 6: Add of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(status=1)
    gramapanchayat = GramaPanchayat.objects.filter(status=1, id__in=panchayat_id)
    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        panchayat_name_id = data.get('panchayat_name')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)

        friendly_club = AdolescentFriendlyClub.objects.create(start_date = date_of_registration, panchayat_name=panchayat_name,
        hsc_name=hsc_name, subject=subject, facilitator=facilitator, designation=designation,
        no_of_sahiya=no_of_sahiya, no_of_aww=no_of_aww, pe_girls_10_14_year=pe_girls_10_14_year,
        pe_girls_15_19_year=pe_girls_15_19_year, pe_boys_10_14_year=pe_boys_10_14_year,
        pe_boys_15_19_year=pe_boys_15_19_year, task=task, site_id = current_site)
        friendly_club.save()
        return redirect('/po-report/fossil/friendly-club-listing/'+str(task_id))
    return render(request, 'po_report/fossil/friendly_club/add_friendly_club.html', locals())



@ login_required(login_url='/login/')
def edit_friendly_club_fossil_po_report(request, friendly_club_id, task_id):
    heading = "Section 6: Edit of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.get(id=friendly_club_id)
    gramapanchayat = GramaPanchayat.objects.filter(status=1, id__in=panchayat_id)
    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        panchayat_name_id = data.get('panchayat_name')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)
        
        friendly_club.start_date = date_of_registration
        friendly_club.panchayat_name_id = panchayat_name
        friendly_club.hsc_name = hsc_name
        friendly_club.subject = subject
        friendly_club.facilitator = facilitator
        friendly_club.designation = designation
        friendly_club.no_of_sahiya = no_of_sahiya
        friendly_club.no_of_aww = no_of_aww
        friendly_club.pe_girls_10_14_year = pe_girls_10_14_year
        friendly_club.pe_girls_15_19_year = pe_girls_15_19_year
        friendly_club.pe_boys_10_14_year = pe_boys_10_14_year
        friendly_club.pe_boys_15_19_year = pe_boys_15_19_year
        friendly_club.task_id = task
        friendly_club.site_id =  current_site
        friendly_club.save()
        return redirect('/po-report/fossil/friendly-club-listing/'+str(task_id))
    return render(request, 'po_report/fossil/friendly_club/edit_friendly_club.html', locals())


@ login_required(login_url='/login/')
def balsansad_meeting_listing_fossil_po_report(request, task_id):
    heading = "Section 7: Details of Bal Sansad meetings conducted"
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.filter(status=1, school_name__id__in=school_id, task__id = task_id)
    data = pagination_function(request, balsansad_meeting)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/bal_sansad_metting/bal_sansad_listing.html', locals())

@ login_required(login_url='/login/')
def add_balsansad_meeting_fossil_po_report(request, task_id):
    heading = "Section 7: Add of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.filter()
    school = School.objects.filter(status=1, id__in=school_id)
    masterlookups_issues_discussion = MasterLookUp.objects.filter(parent__slug = 'issues_discussion')

    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        school_name_id = data.get('school_name')
        school_name = School.objects.get(id=school_name_id)
        no_of_participants = data.get('no_of_participants')
        decision_taken = data.get('decision_taken')
        issues_discussion = data.get('issues_discussion')
        task = Task.objects.get(id=task_id)
        balsansad_meeting = BalSansadMeeting.objects.create(start_date = date_of_registration, school_name=school_name,
        no_of_participants=no_of_participants, decision_taken=decision_taken,
        task=task, site_id = current_site)
        if issues_discussion:
            issues_discussion = MasterLookUp.objects.get(id=issues_discussion)
            balsansad_meeting.issues_discussion = issues_discussion
        balsansad_meeting.save()
        return redirect('/po-report/fossil/balsansad-listing/'+str(task_id))
    return render(request, 'po_report/fossil/bal_sansad_metting/add_bal_sansad.html', locals())


@ login_required(login_url='/login/')
def edit_balsansad_meeting_fossil_po_report(request, balsansad_id, task_id):
    heading = "Section 7: Edit of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.get(id=balsansad_id)
    school = School.objects.filter(status=1, id__in=school_id)
    masterlookups_issues_discussion = MasterLookUp.objects.filter(parent__slug = 'issues_discussion')

    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        school_name_id = data.get('school_name')
        school_name = School.objects.get(id=school_name_id)
        no_of_participants = data.get('no_of_participants')
        decision_taken = data.get('decision_taken')
        issues_discussion = data.get('issues_discussion')
        task = Task.objects.get(id=task_id)
        balsansad_meeting.start_date = date_of_registration
        balsansad_meeting.school_name_id = school_name
        balsansad_meeting.no_of_participants = no_of_participants
        balsansad_meeting.decision_taken = decision_taken
        balsansad_meeting.task_id = task
        balsansad_meeting.site_id =  current_site
        if issues_discussion:
            issues_discussion = MasterLookUp.objects.get(id=issues_discussion)
            balsansad_meeting.issues_discussion = issues_discussion
        balsansad_meeting.save()
        return redirect('/po-report/fossil/balsansad-listing/'+str(task_id))
    return render(request, 'po_report/fossil/bal_sansad_metting/edit_bal_sansad.html', locals())


@ login_required(login_url='/login/')
def community_activities_listing_fossil_po_report(request, task_id):
    heading = "Section 8: Details of community engagement activities"
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.filter(status=1, village_name__id__in=village_id, task__id = task_id)
    data = pagination_function(request, activities)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/community_activities/community_activities_listing.html', locals())


@ login_required(login_url='/login/')
def add_community_activities_fossil_po_report(request, task_id):
    heading = "Section 8: Add of community engagement activities"
    current_site = request.session.get('site_id')
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.filter(status=1,)
    village =  Village.objects.filter(status=1, id__in=village_id )
    masterlookups_event = MasterLookUp.objects.filter(parent__slug = 'event')
    masterlookups_activity = MasterLookUp.objects.filter(parent__slug = 'activities')

    if request.method == 'POST':
        data = request.POST
        village_name_id = data.get('village_name')
        date_of_registration = data.get('date_of_registration')
        village_name = Village.objects.get(id=village_name_id)
        name_of_event_activity = data.get('name_of_event_activity')
        name_of_event_id = data.get('name_of_event')
        name_of_activity_id = data.get('name_of_activity')
        organized_by = data.get('organized_by')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)

        activities =  CommunityEngagementActivities.objects.create(village_name=village_name, start_date = date_of_registration,
        name_of_event_activity=name_of_event_activity, organized_by=organized_by,
        girls_10_14_year=girls_10_14_year, girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year,
        boys_15_19_year=boys_15_19_year, champions_15_19_year=champions_15_19_year, adult_male=adult_male,
        adult_female=adult_female, teachers=teachers, pri_members=pri_members, services_providers=services_providers,
        sms_members=sms_members, other=other, task=task, site_id = current_site)
        
        if name_of_event_id:
            name_of_event = MasterLookUp.objects.get(id = name_of_event_id)
            activities.event_name = name_of_event

        if name_of_activity_id:
            name_of_activity = MasterLookUp.objects.get(id = name_of_activity_id)
            activities.activity_name = name_of_activity
        activities.save()
        return redirect('/po-report/fossil/community-activities-listing/'+str(task_id))
    return render(request, 'po_report/fossil/community_activities/add_community_activities.html', locals())


@ login_required(login_url='/login/')
def edit_community_activities_fossil_po_report(request, activities_id, task_id):
    heading = "Section 8: Edit of community engagement activities"
    current_site = request.session.get('site_id')
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.get(id=activities_id)
    village =  Village.objects.filter(status=1, id__in=village_id)
    masterlookups_event = MasterLookUp.objects.filter(parent__slug = 'event')
    masterlookups_activity = MasterLookUp.objects.filter(parent__slug = 'activities')

    if request.method == 'POST':
        data = request.POST
        village_name_id = data.get('village_name')
        date_of_registration = data.get('date_of_registration')
        village_name = Village.objects.get(id=village_name_id)
        name_of_event_activity = data.get('name_of_event_activity')
        # theme_topic = data.get('theme_topic')
        name_of_event_id = data.get('name_of_event')
        name_of_activity_id = data.get('name_of_activity')

        organized_by = data.get('organized_by')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)

        activities.start_date = date_of_registration
        activities.village_name_id = village_name
        activities.name_of_event_activity = name_of_event_activity
        # activities.theme_topic = theme_topic
        activities.organized_by = organized_by
        activities.boys_10_14_year = boys_10_14_year
        activities.boys_15_19_year = boys_15_19_year
        activities.girls_10_14_year = girls_10_14_year
        activities.girls_15_19_year = girls_15_19_year
        activities.champions_15_19_year = champions_15_19_year
        activities.adult_male = adult_male
        activities.adult_female = adult_female
        activities.teachers = teachers
        activities.pri_members = pri_members
        activities.services_providers = services_providers
        activities.sms_members = sms_members
        activities.other = other
        activities.task_id = task
        activities.site_id =  current_site
        
        if name_of_event_id:
            name_of_event = MasterLookUp.objects.get(id = name_of_event_id)
            activities.event_name = name_of_event

        if name_of_activity_id:
            name_of_activity = MasterLookUp.objects.get(id = name_of_activity_id)
            activities.activity_name = name_of_activity
        activities.save()
        return redirect('/po-report/fossil/community-activities-listing/'+str(task_id))
    return render(request, 'po_report/fossil/community_activities/edit_community_activities.html', locals())


@ login_required(login_url='/login/')
def champions_listing_fossil_po_report(request, task_id):
    heading = "Section 9: Details of exposure visits of adolescent champions"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.filter(status=1, awc_name__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, champions)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/champions/champions_listing.html', locals())





@ login_required(login_url='/login/')
def add_champions_fossil_po_report(request, task_id):
    heading = "Section 9: Add of exposure visits of adolescent champions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.filter()
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        date_of_visit = data.get('date_of_visit')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        first_inst_visited = data.get('first_inst_visited')
        second_inst_visited = data.get('second_inst_visited')
        third_inst_visited = data.get('third_inst_visited')
        fourth_inst_visited = data.get('fourth_inst_visited')
        task = Task.objects.get(id=task_id)

        champions =  Champions.objects.create(awc_name=awc_name,date_of_visit=date_of_visit,  girls_10_14_year=girls_10_14_year,
        girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year, boys_15_19_year=boys_15_19_year,
        first_inst_visited=first_inst_visited,second_inst_visited=second_inst_visited or None,
        third_inst_visited=third_inst_visited or None, fourth_inst_visited=fourth_inst_visited or None,  task=task, site_id = current_site)
        champions.save()
        return redirect('/po-report/fossil/champions-listing/'+str(task_id))
    return render(request, 'po_report/fossil/champions/add_champions.html', locals())


@ login_required(login_url='/login/')
def edit_champions_fossil_po_report(request, champions_id, task_id):
    heading = "Section 9: Edit of exposure visits of adolescent champions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.get(id=champions_id)
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        date_of_visit = data.get('date_of_visit')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        first_inst_visited = data.get('first_inst_visited')
        second_inst_visited = data.get('second_inst_visited')
        third_inst_visited = data.get('third_inst_visited')
        fourth_inst_visited = data.get('fourth_inst_visited')
        task = Task.objects.get(id=task_id)

        champions.awc_name_id = awc_name       
        champions.date_of_visit = date_of_visit 
        champions.girls_10_14_year = girls_10_14_year       
        champions.girls_15_19_year = girls_15_19_year     
        champions.boys_10_14_year = boys_10_14_year       
        champions.boys_15_19_year = boys_15_19_year       
        champions.first_inst_visited = first_inst_visited
        champions.second_inst_visited= second_inst_visited or None
        champions.third_inst_visited = third_inst_visited or None
        champions.fourth_inst_visited = fourth_inst_visited or None
        champions.task_id = task
        champions.site_id =  current_site       
        champions.save()
        return redirect('/po-report/fossil/champions-listing/'+str(task_id))
    return render(request, 'po_report/fossil/champions/edit_champions.html', locals())

@ login_required(login_url='/login/')
def reenrolled_listing_fossil_po_report(request, task_id):
    heading = "Section 10: Details of adolescent re-enrolled in schools"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, adolescent_reenrolled)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/re_enrolled/re_enrolled_listing.html', locals())

@ login_required(login_url='/login/')
def add_reenrolled_fossil_po_report(request, task_id):
    heading = "Section 10: Add of adolescent re-enrolled in schools"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter()
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    # school = School.objects.filter(status=1, id__in = school_id)
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        gender = data.get('gender')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        school_name = data.get('school_name')
        # school_name = School.objects.get(id=school_name_id)
        which_class_enrolled = data.get('which_class_enrolled')
        task = Task.objects.get(id=task_id)

        adolescent_reenrolled =  AdolescentRe_enrolled.objects.create(adolescent_name=adolescent_name,
        gender=gender, age=age, parent_guardian_name=parent_guardian_name, school_name=school_name, which_class_enrolled=which_class_enrolled,
        task=task, site_id = current_site)
        adolescent_reenrolled.save()
        return redirect('/po-report/fossil/reenrolled-listing/'+str(task_id))
    return render(request, 'po_report/fossil/re_enrolled/add_re_enrolled.html', locals())


@ login_required(login_url='/login/')
def edit_reenrolled_fossil_po_report(request, reenrolled_id, task_id):
    heading = "Section 10: Edit of adolescent re-enrolled in schools"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.get(id=reenrolled_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    # school = School.objects.filter()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        gender = data.get('gender')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        school_name = data.get('school_name')
        # school_name = School.objects.get(id=school_name_id)
        which_class_enrolled = data.get('which_class_enrolled')
        task = Task.objects.get(id=task_id)

        adolescent_reenrolled.adolescent_name_id = adolescent_name
        adolescent_reenrolled.gender = gender
        adolescent_reenrolled.age = age
        adolescent_reenrolled.parent_guardian_name = parent_guardian_name
        adolescent_reenrolled.school_name = school_name
        adolescent_reenrolled.which_class_enrolled = which_class_enrolled
        adolescent_reenrolled.task_id = task
        adolescent_reenrolled.site_id =  current_site
        adolescent_reenrolled.save()
        return redirect('/po-report/fossil/reenrolled-listing/'+str(task_id))
    return render(request, 'po_report/fossil/re_enrolled/edit_re_enrolled.html', locals())

@ login_required(login_url='/login/')
def stakeholders_listing_fossil_po_report(request, task_id):
    heading = "Section 11: Details of capacity building of different stakeholders"
    if Stakeholder.objects.filter(task=task_id).exists():
        error="disabled"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    stakeholders_obj = Stakeholder.objects.filter(user_name=request.user.id, task__id = task_id)
    data = pagination_function(request, stakeholders_obj)
    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/stakeholders/stakeholders_listing.html', locals())


@ login_required(login_url='/login/')
def add_stakeholders_fossil_po_report(request, task_id):
    heading = "Section 11: Add of capacity building of different stakeholders"
    current_site = request.session.get('site_id')
    stakeholders_obj = Stakeholder.objects.filter()
    if request.method == 'POST':
        data = request.POST
        master_trainers_male = data.get('master_trainers_male')
        master_trainers_female = data.get('master_trainers_female')
        master_trainers_total = data.get('master_trainers_total')
        nodal_teachers_male = data.get('nodal_teachers_male')
        nodal_teachers_female = data.get('nodal_teachers_female')
        nodal_teachers_total = data.get('nodal_teachers_total')
        principals_male = data.get('principals_male')
        principals_female = data.get('principals_female')
        principals_total = data.get('principals_total')
        district_level_officials_male = data.get('district_level_officials_male')
        district_level_officials_female = data.get('district_level_officials_female')
        district_level_officials_total = data.get('district_level_officials_total')
        peer_educator_male = data.get('peer_educator_male')
        peer_educator_female = data.get('peer_educator_female')
        peer_educator_total = data.get('peer_educator_total')
        state_level_officials_male = data.get('state_level_officials_male')
        state_level_officials_female = data.get('state_level_officials_female')
        state_level_officials_total = data.get('state_level_officials_total')
        icds_awws_male = data.get('icds_awws_male')
        icds_awws_female = data.get('icds_awws_female')
        icds_awws_total = data.get('icds_awws_total')
        icds_supervisors_male = data.get('icds_supervisors_male')
        icds_supervisors_female = data.get('icds_supervisors_female')
        icds_supervisors_total = data.get('icds_supervisors_total')
        icds_peer_educator_male = data.get('icds_peer_educator_male')
        icds_peer_educator_female = data.get('icds_peer_educator_female')
        icds_peer_educator_total = data.get('icds_peer_educator_total')
        icds_child_developement_project_officers_male = data.get('icds_child_developement_project_officers_male')
        icds_child_developement_project_officers_female = data.get('icds_child_developement_project_officers_female')
        icds_child_developement_project_officers_total = data.get('icds_child_developement_project_officers_total')
        icds_district_level_officials_male = data.get('icds_district_level_officials_male')
        icds_district_level_officials_female = data.get('icds_district_level_officials_female')
        icds_district_level_officials_total = data.get('icds_district_level_officials_total')
        icds_state_level_officials_male = data.get('icds_state_level_officials_male')
        icds_state_level_officials_female = data.get('icds_state_level_officials_female')
        icds_state_level_officials_total = data.get('icds_state_level_officials_total')
        health_ashas_male = data.get('health_ashas_male')
        health_ashas_female = data.get('health_ashas_female')
        health_ashas_total = data.get('health_ashas_total')
        health_anms_male = data.get('health_anms_male')
        health_anms_female = data.get('health_anms_female')
        health_anms_total = data.get('health_anms_total')
        health_bpm_bhm_pheos_male = data.get('health_bpm_bhm_pheos_male')
        health_bpm_bhm_pheos_female = data.get('health_bpm_bhm_pheos_female')
        health_bpm_bhm_pheos_total = data.get('health_bpm_bhm_pheos_total')
        health_medical_officers_male = data.get('health_medical_officers_male')
        health_medical_officers_female = data.get('health_medical_officers_female')
        health_medical_officers_total = data.get('health_medical_officers_total')
        health_district_level_officials_male = data.get('health_district_level_officials_male')
        health_district_level_officials_female = data.get('health_district_level_officials_female')
        health_district_level_officials_total = data.get('health_district_level_officials_total')
        health_state_level_officials_male = data.get('health_state_level_officials_male')
        health_state_level_officials_female = data.get('health_state_level_officials_female')
        health_state_level_officials_total = data.get('health_state_level_officials_total')
        health_rsk_male = data.get('health_rsk_male')
        health_rsk_female = data.get('health_rsk_female')
        health_rsk_total = data.get('health_rsk_total')
        health_peer_educator_male = data.get('health_peer_educator_male')
        health_peer_educator_female = data.get('health_peer_educator_female')
        health_peer_educator_total = data.get('health_peer_educator_total')
        panchayat_ward_members_male = data.get('panchayat_ward_members_male')
        panchayat_ward_members_female = data.get('panchayat_ward_members_female')
        panchayat_ward_members_total = data.get('panchayat_ward_members_total')
        panchayat_up_mukhiya_up_Pramukh_male = data.get('panchayat_up_mukhiya_up_Pramukh_male')
        panchayat_up_mukhiya_up_Pramukh_female = data.get('panchayat_up_mukhiya_up_Pramukh_female')
        panchayat_up_mukhiya_up_Pramukh_total = data.get('panchayat_up_mukhiya_up_Pramukh_total')
        panchayat_mukhiya_Pramukh_male = data.get('panchayat_mukhiya_Pramukh_male')
        panchayat_mukhiya_Pramukh_female = data.get('panchayat_mukhiya_Pramukh_female')
        panchayat_mukhiya_Pramukh_total = data.get('panchayat_mukhiya_Pramukh_total')
        panchayat_samiti_member_male = data.get('panchayat_samiti_member_male')
        panchayat_samiti_member_female = data.get('panchayat_samiti_member_female')
        panchayat_samiti_member_total = data.get('panchayat_samiti_member_total')
        panchayat_zila_parishad_member_male = data.get('panchayat_zila_parishad_member_male')
        panchayat_zila_parishad_member_female = data.get('panchayat_zila_parishad_member_female')
        panchayat_zila_parishad_member_total = data.get('panchayat_zila_parishad_member_total')
        panchayat_vc_zila_parishad_male = data.get('panchayat_vc_zila_parishad_male')
        panchayat_vc_zila_parishad_female = data.get('panchayat_vc_zila_parishad_female')
        panchayat_vc_zila_parishad_total = data.get('panchayat_vc_zila_parishad_total')
        panchayat_chairman_zila_parishad_male = data.get('panchayat_chairman_zila_parishad_male')
        panchayat_chairman_zila_parishad_female = data.get('panchayat_chairman_zila_parishad_female')
        panchayat_chairman_zila_parishad_total = data.get('panchayat_chairman_zila_parishad_total')
        panchayat_block_level_officials_male = data.get('panchayat_block_level_officials_male')
        panchayat_block_level_officials_female = data.get('panchayat_block_level_officials_female')
        panchayat_block_level_officials_total = data.get('panchayat_block_level_officials_total')
        panchayat_district_level_officials_male = data.get('panchayat_district_level_officials_male')
        panchayat_district_level_officials_female = data.get('panchayat_district_level_officials_female')
        panchayat_district_level_officials_total = data.get('panchayat_district_level_officials_total')
        panchayat_state_level_officials_male = data.get('panchayat_state_level_officials_male')
        panchayat_state_level_officials_female = data.get('panchayat_state_level_officials_female')
        panchayat_state_level_officials_total = data.get('panchayat_state_level_officials_total')
        media_interns_male = data.get('media_interns_male')
        media_interns_female = data.get('media_interns_female')
        media_interns_total = data.get('media_interns_total')
        media_journalists_male = data.get('media_journalists_male')
        media_journalists_female = data.get('media_journalists_female')
        media_journalists_total = data.get('media_journalists_total')
        media_editors_male = data.get('media_editors_male')
        media_editors_female = data.get('media_editors_female')
        media_editors_total = data.get('media_editors_total')
        others_block_cluster_field_corrdinators_male = data.get('others_block_cluster_field_corrdinators_male')
        others_block_cluster_field_corrdinators_female = data.get('others_block_cluster_field_corrdinators_female')
        others_block_cluster_field_corrdinators_total = data.get('others_block_cluster_field_corrdinators_total')
        others_ngo_staff_corrdinators_male = data.get('others_ngo_staff_corrdinators_male')
        others_ngo_staff_corrdinators_female = data.get('others_ngo_staff_corrdinators_female')
        others_ngo_staff_corrdinators_total = data.get('others_ngo_staff_corrdinators_total')
        others_male = data.get('others_male')
        others_female = data.get('others_female')
        others_total = data.get('others_total')
        total_male = data.get('total_male')
        total_female = data.get('total_female')
        total = data.get('total')
        task = Task.objects.get(id=task_id)

        if total and int(total) != 0:
            stakeholders_obj = Stakeholder.objects.create(user_name=request.user,
            master_trainers_male=master_trainers_male or None, master_trainers_female=master_trainers_female or None, master_trainers_total=master_trainers_total or None,
            nodal_teachers_male=nodal_teachers_male or None, nodal_teachers_female=nodal_teachers_female or None, nodal_teachers_total=nodal_teachers_total or None,
            principals_male=principals_male or None, principals_female=principals_female or None, principals_total=principals_total or None, 
            district_level_officials_male=district_level_officials_male or None, district_level_officials_female=district_level_officials_female or None, district_level_officials_total=district_level_officials_total or None,
            peer_educator_male=peer_educator_male or None, peer_educator_female=peer_educator_female or None, peer_educator_total=peer_educator_total or None,
            state_level_officials_male=state_level_officials_male or None, state_level_officials_female=state_level_officials_female or None, state_level_officials_total=state_level_officials_total or None,
            icds_awws_male=icds_awws_male or None, icds_awws_female=icds_awws_female or None, icds_awws_total=icds_awws_total or None,
            icds_supervisors_male=icds_supervisors_male or None, icds_supervisors_female=icds_supervisors_female or None, icds_supervisors_total=icds_supervisors_total or None,
            icds_peer_educator_male=icds_peer_educator_male or None, icds_peer_educator_female=icds_peer_educator_female or None, icds_peer_educator_total=icds_peer_educator_total or None,
            icds_child_developement_project_officers_male=icds_child_developement_project_officers_male or None, icds_child_developement_project_officers_female=icds_child_developement_project_officers_female or None, icds_child_developement_project_officers_total=icds_child_developement_project_officers_total or None,
            icds_district_level_officials_male=icds_district_level_officials_male or None, icds_district_level_officials_female=icds_district_level_officials_female or None, icds_district_level_officials_total=icds_district_level_officials_total or None,
            icds_state_level_officials_male=icds_state_level_officials_male or None, icds_state_level_officials_female=icds_state_level_officials_female or None, icds_state_level_officials_total=icds_state_level_officials_total or None,
            health_ashas_male=health_ashas_male or None, health_ashas_female=health_ashas_female or None, health_ashas_total=health_ashas_total or None,
            health_anms_male=health_anms_male or None, health_anms_female=health_anms_female or None, health_anms_total=health_anms_total or None,
            health_bpm_bhm_pheos_male=health_bpm_bhm_pheos_male or None, health_bpm_bhm_pheos_female=health_bpm_bhm_pheos_female or None, health_bpm_bhm_pheos_total=health_bpm_bhm_pheos_total or None,
            health_medical_officers_male=health_medical_officers_male or None, health_medical_officers_female=health_medical_officers_female or None, health_medical_officers_total=health_medical_officers_total or None,
            health_district_level_officials_male=health_district_level_officials_male or None, health_district_level_officials_female=health_district_level_officials_female or None, health_district_level_officials_total=health_district_level_officials_total or None,
            health_state_level_officials_male=health_state_level_officials_male or None, health_state_level_officials_female=health_state_level_officials_female or None, health_state_level_officials_total=health_state_level_officials_total or None,
            health_rsk_male=health_rsk_male or None, health_rsk_female=health_rsk_female or None, health_rsk_total=health_rsk_total or None,
            health_peer_educator_male=health_peer_educator_male or None, health_peer_educator_female=health_peer_educator_female or None, health_peer_educator_total=health_peer_educator_total or None,
            panchayat_ward_members_male=panchayat_ward_members_male or None, panchayat_ward_members_female=panchayat_ward_members_female or None, panchayat_ward_members_total=panchayat_ward_members_total or None,
            panchayat_up_mukhiya_up_Pramukh_male=panchayat_up_mukhiya_up_Pramukh_male or None, panchayat_up_mukhiya_up_Pramukh_female=panchayat_up_mukhiya_up_Pramukh_female or None, panchayat_up_mukhiya_up_Pramukh_total=panchayat_up_mukhiya_up_Pramukh_total or None,
            panchayat_mukhiya_Pramukh_male=panchayat_mukhiya_Pramukh_male or None, panchayat_mukhiya_Pramukh_female=panchayat_mukhiya_Pramukh_female or None, panchayat_mukhiya_Pramukh_total=panchayat_mukhiya_Pramukh_total or None,
            panchayat_samiti_member_male=panchayat_samiti_member_male or None, panchayat_samiti_member_female=panchayat_samiti_member_female or None, panchayat_samiti_member_total=panchayat_samiti_member_total or None,
            panchayat_zila_parishad_member_male=panchayat_zila_parishad_member_male or None, panchayat_zila_parishad_member_female=panchayat_zila_parishad_member_female or None, panchayat_zila_parishad_member_total=panchayat_zila_parishad_member_total or None,
            panchayat_vc_zila_parishad_male=panchayat_vc_zila_parishad_male or None, panchayat_vc_zila_parishad_female=panchayat_vc_zila_parishad_female or None, panchayat_vc_zila_parishad_total=panchayat_vc_zila_parishad_total or None,
            panchayat_chairman_zila_parishad_male=panchayat_chairman_zila_parishad_male or None, panchayat_chairman_zila_parishad_female=panchayat_chairman_zila_parishad_female or None, panchayat_chairman_zila_parishad_total=panchayat_chairman_zila_parishad_total or None,
            panchayat_block_level_officials_male=panchayat_block_level_officials_male or None, panchayat_block_level_officials_female=panchayat_block_level_officials_female or None, panchayat_block_level_officials_total=panchayat_block_level_officials_total or None,
            panchayat_district_level_officials_male=panchayat_district_level_officials_male or None, panchayat_district_level_officials_female=panchayat_district_level_officials_female or None, panchayat_district_level_officials_total=panchayat_district_level_officials_total or None,
            panchayat_state_level_officials_male=panchayat_state_level_officials_male or None, panchayat_state_level_officials_female=panchayat_state_level_officials_female or None, panchayat_state_level_officials_total=panchayat_state_level_officials_total or None,
            media_interns_male=media_interns_male or None, media_interns_female=media_interns_female or None, media_interns_total=media_interns_total or None,
            media_journalists_male=media_journalists_male or None, media_journalists_female=media_journalists_female or None, media_journalists_total=media_journalists_total or None,
            media_editors_male=media_editors_male or None, media_editors_female=media_editors_female or None, media_editors_total=media_editors_total or None,
            others_block_cluster_field_corrdinators_male=others_block_cluster_field_corrdinators_male or None, others_block_cluster_field_corrdinators_female=others_block_cluster_field_corrdinators_female or None, others_block_cluster_field_corrdinators_total=others_block_cluster_field_corrdinators_total or None,
            others_ngo_staff_corrdinators_male=others_ngo_staff_corrdinators_male or None, others_ngo_staff_corrdinators_female=others_ngo_staff_corrdinators_female or None, others_ngo_staff_corrdinators_total=others_ngo_staff_corrdinators_total or None,
            others_male=others_male or None, others_female=others_female or None, others_total=others_total or None,
            total_male=total_male or None, total_female=total_female or None, total=total, task=task, site_id = current_site,
            )
            stakeholders_obj.save()
            return redirect('/po-report/rnp/stakeholders-listing/'+str(task_id))
        else:
            error_message = 'Please, Enter the any one Category of participants for Achieved in this month'
    return render(request, 'po_report/fossil/stakeholders/add_stakeholders.html', locals())


@ login_required(login_url='/login/')
def edit_stakeholders_fossil_po_report(request, stakeholders_id, task_id):
    heading = "Section 11: Edit of capacity building of different stakeholders"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    stakeholders_obj = Stakeholder.objects.get(id=stakeholders_id)
    if request.method == 'POST':
        data = request.POST
        master_trainers_male = data.get('master_trainers_male')
        master_trainers_female = data.get('master_trainers_female')
        master_trainers_total = data.get('master_trainers_total')
        nodal_teachers_male = data.get('nodal_teachers_male')
        nodal_teachers_female = data.get('nodal_teachers_female')
        nodal_teachers_total = data.get('nodal_teachers_total')
        principals_male = data.get('principals_male')
        principals_female = data.get('principals_female')
        principals_total = data.get('principals_total')
        district_level_officials_male = data.get('district_level_officials_male')
        district_level_officials_female = data.get('district_level_officials_female')
        district_level_officials_total = data.get('district_level_officials_total')
        peer_educator_male = data.get('peer_educator_male')
        peer_educator_female = data.get('peer_educator_female')
        peer_educator_total = data.get('peer_educator_total')
        state_level_officials_male = data.get('state_level_officials_male')
        state_level_officials_female = data.get('state_level_officials_female')
        state_level_officials_total = data.get('state_level_officials_total')
        icds_awws_male = data.get('icds_awws_male')
        icds_awws_female = data.get('icds_awws_female')
        icds_awws_total = data.get('icds_awws_total')
        icds_supervisors_male = data.get('icds_supervisors_male')
        icds_supervisors_female = data.get('icds_supervisors_female')
        icds_supervisors_total = data.get('icds_supervisors_total')
        icds_peer_educator_male = data.get('icds_peer_educator_male')
        icds_peer_educator_female = data.get('icds_peer_educator_female')
        icds_peer_educator_total = data.get('icds_peer_educator_total')
        icds_child_developement_project_officers_male = data.get('icds_child_developement_project_officers_male')
        icds_child_developement_project_officers_female = data.get('icds_child_developement_project_officers_female')
        icds_child_developement_project_officers_total = data.get('icds_child_developement_project_officers_total')
        icds_district_level_officials_male = data.get('icds_district_level_officials_male')
        icds_district_level_officials_female = data.get('icds_district_level_officials_female')
        icds_district_level_officials_total = data.get('icds_district_level_officials_total')
        icds_state_level_officials_male = data.get('icds_state_level_officials_male')
        icds_state_level_officials_female = data.get('icds_state_level_officials_female')
        icds_state_level_officials_total = data.get('icds_state_level_officials_total')
        health_ashas_male = data.get('health_ashas_male')
        health_ashas_female = data.get('health_ashas_female')
        health_ashas_total = data.get('health_ashas_total')
        health_anms_male = data.get('health_anms_male')
        health_anms_female = data.get('health_anms_female')
        health_anms_total = data.get('health_anms_total')
        health_bpm_bhm_pheos_male = data.get('health_bpm_bhm_pheos_male')
        health_bpm_bhm_pheos_female = data.get('health_bpm_bhm_pheos_female')
        health_bpm_bhm_pheos_total = data.get('health_bpm_bhm_pheos_total')
        health_medical_officers_male = data.get('health_medical_officers_male')
        health_medical_officers_female = data.get('health_medical_officers_female')
        health_medical_officers_total = data.get('health_medical_officers_total')
        health_district_level_officials_male = data.get('health_district_level_officials_male')
        health_district_level_officials_female = data.get('health_district_level_officials_female')
        health_district_level_officials_total = data.get('health_district_level_officials_total')
        health_state_level_officials_male = data.get('health_state_level_officials_male')
        health_state_level_officials_female = data.get('health_state_level_officials_female')
        health_state_level_officials_total = data.get('health_state_level_officials_total')
        health_rsk_male = data.get('health_rsk_male')
        health_rsk_female = data.get('health_rsk_female')
        health_rsk_total = data.get('health_rsk_total')
        health_peer_educator_male = data.get('health_peer_educator_male')
        health_peer_educator_female = data.get('health_peer_educator_female')
        health_peer_educator_total = data.get('health_peer_educator_total')
        panchayat_ward_members_male = data.get('panchayat_ward_members_male')
        panchayat_ward_members_female = data.get('panchayat_ward_members_female')
        panchayat_ward_members_total = data.get('panchayat_ward_members_total')
        panchayat_up_mukhiya_up_Pramukh_male = data.get('panchayat_up_mukhiya_up_Pramukh_male')
        panchayat_up_mukhiya_up_Pramukh_female = data.get('panchayat_up_mukhiya_up_Pramukh_female')
        panchayat_up_mukhiya_up_Pramukh_total = data.get('panchayat_up_mukhiya_up_Pramukh_total')
        panchayat_mukhiya_Pramukh_male = data.get('panchayat_mukhiya_Pramukh_male')
        panchayat_mukhiya_Pramukh_female = data.get('panchayat_mukhiya_Pramukh_female')
        panchayat_mukhiya_Pramukh_total = data.get('panchayat_mukhiya_Pramukh_total')
        panchayat_samiti_member_male = data.get('panchayat_samiti_member_male')
        panchayat_samiti_member_female = data.get('panchayat_samiti_member_female')
        panchayat_samiti_member_total = data.get('panchayat_samiti_member_total')
        panchayat_zila_parishad_member_male = data.get('panchayat_zila_parishad_member_male')
        panchayat_zila_parishad_member_female = data.get('panchayat_zila_parishad_member_female')
        panchayat_zila_parishad_member_total = data.get('panchayat_zila_parishad_member_total')
        panchayat_vc_zila_parishad_male = data.get('panchayat_vc_zila_parishad_male')
        panchayat_vc_zila_parishad_female = data.get('panchayat_vc_zila_parishad_female')
        panchayat_vc_zila_parishad_total = data.get('panchayat_vc_zila_parishad_total')
        panchayat_chairman_zila_parishad_male = data.get('panchayat_chairman_zila_parishad_male')
        panchayat_chairman_zila_parishad_female = data.get('panchayat_chairman_zila_parishad_female')
        panchayat_chairman_zila_parishad_total = data.get('panchayat_chairman_zila_parishad_total')
        panchayat_block_level_officials_male = data.get('panchayat_block_level_officials_male')
        panchayat_block_level_officials_female = data.get('panchayat_block_level_officials_female')
        panchayat_block_level_officials_total = data.get('panchayat_block_level_officials_total')
        panchayat_district_level_officials_male = data.get('panchayat_district_level_officials_male')
        panchayat_district_level_officials_female = data.get('panchayat_district_level_officials_female')
        panchayat_district_level_officials_total = data.get('panchayat_district_level_officials_total')
        panchayat_state_level_officials_male = data.get('panchayat_state_level_officials_male')
        panchayat_state_level_officials_female = data.get('panchayat_state_level_officials_female')
        panchayat_state_level_officials_total = data.get('panchayat_state_level_officials_total')
        media_interns_male = data.get('media_interns_male')
        media_interns_female = data.get('media_interns_female')
        media_interns_total = data.get('media_interns_total')
        media_journalists_male = data.get('media_journalists_male')
        media_journalists_female = data.get('media_journalists_female')
        media_journalists_total = data.get('media_journalists_total')
        media_editors_male = data.get('media_editors_male')
        media_editors_female = data.get('media_editors_female')
        media_editors_total = data.get('media_editors_total')
        others_block_cluster_field_corrdinators_male = data.get('others_block_cluster_field_corrdinators_male')
        others_block_cluster_field_corrdinators_female = data.get('others_block_cluster_field_corrdinators_female')
        others_block_cluster_field_corrdinators_total = data.get('others_block_cluster_field_corrdinators_total')
        others_ngo_staff_corrdinators_male = data.get('others_ngo_staff_corrdinators_male')
        others_ngo_staff_corrdinators_female = data.get('others_ngo_staff_corrdinators_female')
        others_ngo_staff_corrdinators_total = data.get('others_ngo_staff_corrdinators_total')
        others_male = data.get('others_male')
        others_female = data.get('others_female')
        others_total = data.get('others_total')
        total_male = data.get('total_male')
        total_female = data.get('total_female')
        total = data.get('total')
        task = Task.objects.get(id=task_id)

        if total and int(total) != 0:
            stakeholders_obj.user_name_id = request.user
            stakeholders_obj.master_trainers_male = master_trainers_male or None
            stakeholders_obj.master_trainers_female = master_trainers_female or None
            stakeholders_obj.master_trainers_total = master_trainers_total or None
            stakeholders_obj.nodal_teachers_male = nodal_teachers_male or None
            stakeholders_obj.nodal_teachers_female = nodal_teachers_female or None
            stakeholders_obj.nodal_teachers_total = nodal_teachers_total or None
            stakeholders_obj.principals_male = principals_male or None
            stakeholders_obj.principals_female = principals_female or None
            stakeholders_obj.principals_total = principals_total or None
            stakeholders_obj.district_level_officials_male = district_level_officials_male or None
            stakeholders_obj.district_level_officials_female = district_level_officials_female or None
            stakeholders_obj.district_level_officials_total = district_level_officials_total or None
            stakeholders_obj.peer_educator_male = peer_educator_male or None
            stakeholders_obj.peer_educator_female = peer_educator_female or None
            stakeholders_obj.peer_educator_total = peer_educator_total or None
            stakeholders_obj.state_level_officials_male = state_level_officials_male or None
            stakeholders_obj.state_level_officials_female = state_level_officials_female or None
            stakeholders_obj.state_level_officials_total = state_level_officials_total or None
            stakeholders_obj.icds_awws_male = icds_awws_male or None
            stakeholders_obj.icds_awws_female = icds_awws_female or None
            stakeholders_obj.icds_awws_total = icds_awws_total or None
            stakeholders_obj.icds_supervisors_male = icds_supervisors_male or None
            stakeholders_obj.icds_supervisors_female = icds_supervisors_female or None
            stakeholders_obj.icds_supervisors_total = icds_supervisors_total or None
            stakeholders_obj.icds_peer_educator_male = icds_peer_educator_male or None
            stakeholders_obj.icds_peer_educator_female = icds_peer_educator_female or None
            stakeholders_obj.icds_peer_educator_total = icds_peer_educator_total or None
            stakeholders_obj.icds_child_developement_project_officers_male = icds_child_developement_project_officers_male or None
            stakeholders_obj.icds_child_developement_project_officers_female = icds_child_developement_project_officers_female or None
            stakeholders_obj.icds_child_developement_project_officers_total = icds_child_developement_project_officers_total or None
            stakeholders_obj.icds_district_level_officials_male = icds_district_level_officials_male or None
            stakeholders_obj.icds_district_level_officials_female = icds_district_level_officials_female or None
            stakeholders_obj.icds_district_level_officials_total = icds_district_level_officials_total or None
            stakeholders_obj.icds_state_level_officials_male = icds_state_level_officials_male or None
            stakeholders_obj.icds_state_level_officials_female = icds_state_level_officials_female or None
            stakeholders_obj.icds_state_level_officials_total = icds_state_level_officials_total or None
            stakeholders_obj.health_ashas_male = health_ashas_male or None
            stakeholders_obj.health_ashas_female = health_ashas_female or None
            stakeholders_obj.health_ashas_total = health_ashas_total or None
            stakeholders_obj.health_anms_male = health_anms_male or None
            stakeholders_obj.health_anms_female = health_anms_female or None
            stakeholders_obj.health_anms_total = health_anms_total or None
            stakeholders_obj.health_bpm_bhm_pheos_male = health_bpm_bhm_pheos_male or None
            stakeholders_obj.health_bpm_bhm_pheos_female = health_bpm_bhm_pheos_female or None
            stakeholders_obj.health_bpm_bhm_pheos_total = health_bpm_bhm_pheos_total or None
            stakeholders_obj.health_medical_officers_male = health_medical_officers_male or None
            stakeholders_obj.health_medical_officers_female = health_medical_officers_female or None
            stakeholders_obj.health_medical_officers_total = health_medical_officers_total or None
            stakeholders_obj.health_district_level_officials_male = health_district_level_officials_male or None
            stakeholders_obj.health_district_level_officials_female = health_district_level_officials_female or None
            stakeholders_obj.health_district_level_officials_total = health_district_level_officials_total or None
            stakeholders_obj.health_state_level_officials_male = health_state_level_officials_male or None
            stakeholders_obj.health_state_level_officials_female = health_state_level_officials_female or None
            stakeholders_obj.health_state_level_officials_total = health_state_level_officials_total or None
            stakeholders_obj.health_rsk_male = health_rsk_male or None
            stakeholders_obj.health_rsk_female = health_rsk_female or None
            stakeholders_obj.health_rsk_total = health_rsk_total or None
            stakeholders_obj.health_peer_educator_male = health_peer_educator_male or None
            stakeholders_obj.health_peer_educator_female = health_peer_educator_female or None
            stakeholders_obj.health_peer_educator_total = health_peer_educator_total or None
            stakeholders_obj.panchayat_ward_members_male = panchayat_ward_members_male or None
            stakeholders_obj.panchayat_ward_members_female = panchayat_ward_members_female or None
            stakeholders_obj.panchayat_ward_members_total = panchayat_ward_members_total or None
            stakeholders_obj.panchayat_up_mukhiya_up_Pramukh_male = panchayat_up_mukhiya_up_Pramukh_male or None
            stakeholders_obj.panchayat_up_mukhiya_up_Pramukh_female = panchayat_up_mukhiya_up_Pramukh_female or None
            stakeholders_obj.panchayat_up_mukhiya_up_Pramukh_total = panchayat_up_mukhiya_up_Pramukh_total or None
            stakeholders_obj.panchayat_mukhiya_Pramukh_male = panchayat_mukhiya_Pramukh_male or None
            stakeholders_obj.panchayat_mukhiya_Pramukh_female = panchayat_mukhiya_Pramukh_female or None
            stakeholders_obj.panchayat_mukhiya_Pramukh_total = panchayat_mukhiya_Pramukh_total or None
            stakeholders_obj.panchayat_samiti_member_male = panchayat_samiti_member_male or None
            stakeholders_obj.panchayat_samiti_member_female = panchayat_samiti_member_female or None
            stakeholders_obj.panchayat_samiti_member_male = panchayat_samiti_member_total or None
            stakeholders_obj.panchayat_zila_parishad_member_male = panchayat_zila_parishad_member_male or None
            stakeholders_obj.panchayat_zila_parishad_member_female = panchayat_zila_parishad_member_female or None
            stakeholders_obj.panchayat_zila_parishad_member_total = panchayat_zila_parishad_member_total or None
            stakeholders_obj.panchayat_vc_zila_parishad_male = panchayat_vc_zila_parishad_male or None
            stakeholders_obj.panchayat_vc_zila_parishad_female = panchayat_vc_zila_parishad_female or None
            stakeholders_obj.panchayat_vc_zila_parishad_total = panchayat_vc_zila_parishad_total or None
            stakeholders_obj.panchayat_chairman_zila_parishad_male = panchayat_chairman_zila_parishad_male or None
            stakeholders_obj.panchayat_chairman_zila_parishad_female = panchayat_chairman_zila_parishad_female or None
            stakeholders_obj.panchayat_chairman_zila_parishad_total = panchayat_chairman_zila_parishad_total or None
            stakeholders_obj.panchayat_block_level_officials_male = panchayat_block_level_officials_male or None
            stakeholders_obj.panchayat_block_level_officials_female = panchayat_block_level_officials_female or None
            stakeholders_obj.panchayat_block_level_officials_total = panchayat_block_level_officials_total or None
            stakeholders_obj.panchayat_district_level_officials_male = panchayat_district_level_officials_male or None
            stakeholders_obj.panchayat_district_level_officials_female = panchayat_district_level_officials_female or None
            stakeholders_obj.panchayat_district_level_officials_total = panchayat_district_level_officials_total or None
            stakeholders_obj.panchayat_state_level_officials_male = panchayat_state_level_officials_male or None
            stakeholders_obj.panchayat_state_level_officials_female = panchayat_state_level_officials_female or None
            stakeholders_obj.panchayat_state_level_officials_total = panchayat_state_level_officials_total or None
            stakeholders_obj.media_interns_male = media_interns_male or None
            stakeholders_obj.media_interns_female = media_interns_female or None
            stakeholders_obj.media_interns_total = media_interns_total or None
            stakeholders_obj.media_journalists_male = media_journalists_male or None
            stakeholders_obj.media_journalists_female = media_journalists_female or None
            stakeholders_obj.media_journalists_total = media_journalists_total or None
            stakeholders_obj.media_editors_male = media_editors_male or None
            stakeholders_obj.media_editors_female = media_editors_female or None
            stakeholders_obj.media_editors_total = media_editors_total or None
            stakeholders_obj.others_block_cluster_field_corrdinators_male = others_block_cluster_field_corrdinators_male or None
            stakeholders_obj.others_block_cluster_field_corrdinators_female = others_block_cluster_field_corrdinators_female or None
            stakeholders_obj.others_block_cluster_field_corrdinators_total = others_block_cluster_field_corrdinators_total or None
            stakeholders_obj.others_ngo_staff_corrdinators_male = others_ngo_staff_corrdinators_male or None
            stakeholders_obj.others_ngo_staff_corrdinators_female = others_ngo_staff_corrdinators_female or None
            stakeholders_obj.others_ngo_staff_corrdinators_total = others_ngo_staff_corrdinators_total or None
            stakeholders_obj.others_male = others_male or None
            stakeholders_obj.others_female = others_female or None
            stakeholders_obj.others_total = others_total or None
            stakeholders_obj.total_male = total_male or None
            stakeholders_obj.total_female = total_female or None
            stakeholders_obj.total = total or None
            stakeholders_obj.task_id = task
            stakeholders_obj.site_id =  current_site
            stakeholders_obj.save()
            return redirect('/po-report/rnp/stakeholders-listing/'+str(task_id))
        else:
            error_message = 'Please, Enter the any one Category of participants for Achieved in this month'
    return render(request, 'po_report/fossil/stakeholders/edit_stakeholders.html', locals())


@ login_required(login_url='/login/')
def sessions_monitoring_listing_fossil_po_report(request, task_id):
    heading = "Section 12: Details of sessions monitoring and handholding support at block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    village_id =CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    sessions_monitoring = SessionMonitoring.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, sessions_monitoring)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/sessions_monitoring/sessions_monitoring_listing.html', locals())


@ login_required(login_url='/login/')
def add_sessions_monitoring_fossil_po_report(request, task_id):
    heading = "Section 12: Add of sessions monitoring and handholding support at block level"
    current_site = request.session.get('site_id')
    user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    user_report_spo = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    village_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__id')
    school_id = CC_School.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('school__id')
    sessions_monitoring = SessionMonitoring.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    village_obj = Village.objects.filter(status=1, id__in=village_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        name_of_visited = data.get('name_of_visited')
        selected_field_other = data.get('selected_field_other')
        
        if name_of_visited == '1':
            content_type_model='village'
            selected_object_id=data.get('selected_field_village')
        elif name_of_visited == '2':
            content_type_model='awc'
            selected_object_id=data.get('selected_field_awc')
        else:
            content_type_model='school'
            selected_object_id=data.get('selected_field_school')

        date = data.get('date')
      
        sessions = data.getlist('session_attended')
        session_attended = ", ".join(sessions)
        observation = data.get('observation')
        recommendation = data.get('recommendation')
        task = Task.objects.get(id=task_id)

        sessions_monitoring = SessionMonitoring.objects.create(name_of_visited=name_of_visited, session_attended=session_attended,
        date=date,
        observation=observation, recommendation=recommendation, task=task, site_id = current_site)
        
        if selected_object_id:
            content_type = ContentType.objects.get(model=content_type_model)
            sessions_monitoring.content_type=content_type
            sessions_monitoring.object_id=selected_object_id
        
        if name_of_visited in ['4','5']:
            sessions_monitoring.name_of_place_visited = selected_field_other

        sessions_monitoring.save()
        return redirect('/po-report/fossil/sessions-monitoring-listing/'+str(task_id))
    return render(request, 'po_report/fossil/sessions_monitoring/add_sessions_monitoring.html', locals())


@ login_required(login_url='/login/')
def edit_sessions_monitoring_fossil_po_report(request, sessions_id, task_id):
    heading = "Section 12: Edit of sessions monitoring and handholding support at block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    user_report_spo = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    village_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__id')
    school_id = CC_School.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('school__id')
    sessions_monitoring = SessionMonitoring.objects.get(id=sessions_id)
    session_choice = sessions_monitoring.session_attended.split(', ')
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    village_obj = Village.objects.filter(status=1, id__in=village_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        selected_field_other = data.get('selected_field_other')
        name_of_visited = data.get('name_of_visited')
        
        if name_of_visited == '1':
            content_type_model='village'
            selected_object_id=data.get('selected_field_village')
        elif name_of_visited == '2':
            content_type_model='awc'
            selected_object_id=data.get('selected_field_awc')
        else:
            content_type_model='school'
            selected_object_id=data.get('selected_field_school')

        content_type = ContentType.objects.get(model=content_type_model)
        date = data.get('date')
        sessions = data.getlist('session_attended')
        session_attended = ", ".join(sessions)
        observation = data.get('observation')
        recommendation = data.get('recommendation')
        task = Task.objects.get(id=task_id)

        sessions_monitoring.name_of_visited = name_of_visited

        if selected_object_id:
            content_type = ContentType.objects.get(model=content_type_model)
            sessions_monitoring.content_type=content_type
            sessions_monitoring.object_id=selected_object_id

        if name_of_visited in ['4','5']:
            sessions_monitoring.name_of_place_visited = selected_field_other

        sessions_monitoring.date = date
        sessions_monitoring.session_attended = session_attended
        sessions_monitoring.observation = observation
        sessions_monitoring.recommendation = recommendation
        sessions_monitoring.task_id = task
        sessions_monitoring.site_id =  current_site
        sessions_monitoring.save()
        return redirect('/po-report/fossil/sessions-monitoring-listing/'+str(task_id))
    return render(request, 'po_report/fossil/sessions_monitoring/edit_sessions_monitoring.html', locals())



@ login_required(login_url='/login/')
def facility_visits_listing_fossil_po_report(request, task_id):
    heading = "Section 13: Details of events & facility visits at block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    village_id =CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    facility_visits = Events.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, facility_visits)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/facility_visits/facility_visits_listing.html', locals())


@ login_required(login_url='/login/')
def add_facility_visits_fossil_po_report(request, task_id):
    heading = "Section 13: Add of events & facility visits at block level"
    current_site = request.session.get('site_id')
    user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    user_report_spo = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    village_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__id')
    school_id = CC_School.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('school__id')
    facility_visits = Events.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    village_obj = Village.objects.filter(status=1, id__in=village_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        name_of_visited = data.get('name_of_visited')
        selected_field_other = data.get('selected_field_other')
        if name_of_visited == '1':
            content_type_model='village'
            selected_object_id=data.get('selected_field_village')
        elif name_of_visited == '2':
            content_type_model='awc'
            selected_object_id=data.get('selected_field_awc')
        else:
            content_type_model='school'
            selected_object_id=data.get('selected_field_school')

        date = data.get('date')
        purpose_visited = data.get('purpose_visited')
        observation = data.get('observation')
        recommendation = data.get('recommendation')
        task = Task.objects.get(id=task_id)

        
        facility_visits = Events.objects.create(name_of_visited=name_of_visited, purpose_visited=purpose_visited,
        date=date,
        observation=observation, recommendation=recommendation, task=task, site_id = current_site)
        
        if selected_object_id:
            content_type = ContentType.objects.get(model=content_type_model)
            facility_visits.content_type=content_type
            facility_visits.object_id=selected_object_id

        if name_of_visited in ['4','5','6','7','8','9','10','11']:
            facility_visits.name_of_place_visited = selected_field_other

        facility_visits.save()
        return redirect('/po-report/fossil/facility-visits-listing/'+str(task_id))
    return render(request, 'po_report/fossil/facility_visits/add_facility_visits.html', locals())


@ login_required(login_url='/login/')
def edit_facility_visits_fossil_po_report(request, facility_id, task_id):
    heading = "Section 13: Edit of events & facility visits at block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    user_report_spo = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    village_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__id')
    school_id = CC_School.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('school__id')
    facility_visits = Events.objects.get(id=facility_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    village_obj = Village.objects.filter(status=1, id__in=village_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        name_of_visited = data.get('name_of_visited')
        selected_field_other = data.get('selected_field_other')
        if name_of_visited == '1':
            content_type_model='village'
            selected_object_id=data.get('selected_field_village')
        elif name_of_visited == '2':
            content_type_model='awc'
            selected_object_id=data.get('selected_field_awc')
        else:
            content_type_model='school'
            selected_object_id=data.get('selected_field_school')

        date = data.get('date')
        purpose_visited = data.get('purpose_visited')
        observation = data.get('observation')
        recommendation = data.get('recommendation')
        task = Task.objects.get(id=task_id)

        facility_visits.name_of_visited = name_of_visited

        if selected_object_id:
            content_type = ContentType.objects.get(model=content_type_model)
            facility_visits.content_type = content_type
            facility_visits.object_id = selected_object_id
        
        if name_of_visited in ['4','5','6','7','8','9','10','11',]:
            facility_visits.name_of_place_visited = selected_field_other

        facility_visits.date = date
        facility_visits.purpose_visited = purpose_visited
        facility_visits.observation = observation
        facility_visits.recommendation = recommendation
        facility_visits.task_id = task
        facility_visits.site_id =  current_site
        facility_visits.save()
        return redirect('/po-report/fossil/facility-visits-listing/'+str(task_id))
    return render(request, 'po_report/fossil/facility_visits/edit_facility_visits.html', locals())



@ login_required(login_url='/login/')
def followup_liaision_listing_fossil_po_report(request, task_id):
    heading = "Section 15: Details of one to one (Follow up/ Liaison) meetings at district & Block Level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    followup_liaision = FollowUP_LiaisionMeeting.objects.filter(user_name=request.user.id, task__id = task_id)
    data = pagination_function(request, followup_liaision)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/followup_liaision/followup_liaision_listing.html', locals())


@ login_required(login_url='/login/')
def add_followup_liaision_fossil_po_report(request, task_id):
    heading = "Section 15: Add of one to one (Follow up/ Liaison) meetings at district & Block Level"
    current_site = request.session.get('site_id')
    followup_liaision = FollowUP_LiaisionMeeting.objects.filter()
    meeting_obj = MasterLookUp.objects.filter(parent__slug = 'meeting-with-designation')
    if request.method == 'POST':
        data = request.POST
        date = data.get('date')
        district_block_level = data.get('district_block_level')
        meeting_id = data.get('meeting')
        meeting = MasterLookUp.objects.get(id = meeting_id)
        departments = data.get('departments')
        point_of_discussion = data.get('point_of_discussion')
        outcome = data.get('outcome')
        decision_taken = data.get('decision_taken')
        remarks = data.get('remarks')
        task = Task.objects.get(id=task_id)

        followup_liaision = FollowUP_LiaisionMeeting.objects.create(user_name=request.user, date=date,
        district_block_level=district_block_level, meeting_name=meeting, departments=departments, point_of_discussion=point_of_discussion,
        outcome=outcome, decision_taken=decision_taken, remarks=remarks, site_id = current_site, task=task)
        followup_liaision.save()
        return redirect('/po-report/fossil/followup-liaision-listing/'+str(task_id))
    return render(request, 'po_report/fossil/followup_liaision/add_followup_liaision.html', locals())


@ login_required(login_url='/login/')
def edit_followup_liaision_fossil_po_report(request, followup_liaision_id, task_id):
    heading = "Section 15: Edit of one to one (Follow up/ Liaison) meetings at district & Block Level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    followup_liaision = FollowUP_LiaisionMeeting.objects.get(id=followup_liaision_id)
    meeting_obj = MasterLookUp.objects.filter(parent__slug = 'meeting-with-designation')
    if request.method == 'POST':
        data = request.POST
        date = data.get('date')
        district_block_level = data.get('district_block_level')
        meeting_id = data.get('meeting')
        meeting = MasterLookUp.objects.get(id = meeting_id)
        departments = data.get('departments')
        point_of_discussion = data.get('point_of_discussion')
        outcome = data.get('outcome')
        decision_taken = data.get('decision_taken')
        remarks = data.get('remarks')
        task = Task.objects.get(id=task_id)


        followup_liaision.user_name = request.user
        followup_liaision.date = date
        followup_liaision.district_block_level = district_block_level
        followup_liaision.meeting_name = meeting
        followup_liaision.departments = departments
        followup_liaision.point_of_discussion = point_of_discussion
        followup_liaision.outcome = outcome
        followup_liaision.decision_taken = decision_taken
        followup_liaision.remarks = remarks
        followup_liaision.task_id = task
        followup_liaision.site_id =  current_site
        followup_liaision.save()
        return redirect('/po-report/fossil/followup-liaision-listing/'+str(task_id))
    return render(request, 'po_report/fossil/followup_liaision/edit_followup_liaision.html', locals())



@ login_required(login_url='/login/')
def participating_meeting_listing_fossil_po_report(request, task_id):
    heading = "Section 14: Details of participating in meetings at district and block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    participating_meeting = ParticipatingMeeting.objects.filter(user_name=request.user.id, task__id = task_id)
    data = pagination_function(request, participating_meeting)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/participating_meeting/participating_meeting_listing.html', locals())

@ login_required(login_url='/login/')
def add_participating_meeting_fossil_po_report(request, task_id):
    heading = "Section 14: Add of participating in meetings at district and block level"
    current_site = request.session.get('site_id')
    participating_meeting = ParticipatingMeeting.objects.filter()
    if request.method == 'POST':
        data = request.POST
        type_of_meeting = data.get('type_of_meeting')
        department = data.get('department')
        district_block_level = data.get('district_block_level')
        point_of_discussion = data.get('point_of_discussion')
        districit_level_officials = data.get('districit_level_officials')
        block_level = data.get('block_level')
        cluster_level = data.get('cluster_level')
        no_of_pri = data.get('no_of_pri')
        no_of_others = data.get('no_of_others')
        date = data.get('date')
        task = Task.objects.get(id=task_id)
        participating_meeting = ParticipatingMeeting.objects.create(user_name=request.user, type_of_meeting=type_of_meeting,
        departments=departments, point_of_discussion=point_of_discussion, districit_level_officials=districit_level_officials,
        block_level=block_level, cluster_level=cluster_level, no_of_pri=no_of_pri, no_of_others=no_of_others,
        district_block_level=district_block_level, date=date, task=task, site_id = current_site,)
        participating_meeting.save()
        return redirect('/po-report/fossil/participating-meeting-listing/'+str(task_id))
    return render(request, 'po_report/fossil/participating_meeting/add_participating_meeting.html', locals())

@ login_required(login_url='/login/')
def edit_participating_meeting_fossil_po_report(request, participating_id, task_id):
    heading = "Section 14: Edit of participating in meetings at district and block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    participating_meeting = ParticipatingMeeting.objects.get(id=participating_id)
    if request.method == 'POST':
        data = request.POST
        type_of_meeting = data.get('type_of_meeting')
        department = data.get('department')
        district_block_level = data.get('district_block_level')
        point_of_discussion = data.get('point_of_discussion')
        districit_level_officials = data.get('districit_level_officials')
        block_level = data.get('block_level')
        cluster_level = data.get('cluster_level')
        no_of_pri = data.get('no_of_pri')
        no_of_others = data.get('no_of_others')
        date = data.get('date')
        task = Task.objects.get(id=task_id)

        participating_meeting.user_name_id = request.user
        participating_meeting.type_of_meeting = type_of_meeting
        participating_meeting.district_block_level = district_block_level
        participating_meeting.department = department
        participating_meeting.point_of_discussion = point_of_discussion
        participating_meeting.districit_level_officials = districit_level_officials
        participating_meeting.block_level = block_level
        participating_meeting.cluster_level = cluster_level
        participating_meeting.no_of_pri = no_of_pri
        participating_meeting.no_of_others = no_of_others
        participating_meeting.date = date
        participating_meeting.task_id = task
        participating_meeting.site_id =  current_site
        participating_meeting.save()
        return redirect('/po-report/fossil/participating-meeting-listing/'+str(task_id))
    return render(request, 'po_report/fossil/participating_meeting/edit_participating_meeting.html', locals())

@ login_required(login_url='/login/')
def faced_related_listing_fossil_po_report(request, task_id):
    heading = "Section 16: Details of faced related"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    faced_related = FacedRelatedOperation.objects.filter(user_name=request.user.id, task__id = task_id)
    data = pagination_function(request, faced_related)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/fossil/faced_related/faced_related_listing.html', locals())

@ login_required(login_url='/login/')
def add_faced_related_fossil_po_report(request, task_id):
    heading = "Section 16: Add of faced related"
    current_site = request.session.get('site_id')
    faced_related = FacedRelatedOperation.objects.filter()
    if request.method == 'POST':
        data = request.POST
        challenges = data.get('challenges')
        proposed_solution = data.get('proposed_solution')
        task = Task.objects.get(id=task_id)
        if challenges and proposed_solution:
            faced_related = FacedRelatedOperation.objects.create(user_name=request.user, challenges=challenges,
            proposed_solution=proposed_solution, task=task, site_id = current_site)
            faced_related.save()
        else:
            return redirect('/po-report/fossil/faced-related-listing/'+str(task_id))
        return redirect('/po-report/fossil/faced-related-listing/'+str(task_id))
    return render(request, 'po_report/fossil/faced_related/add_faced_related.html', locals())


@ login_required(login_url='/login/')
def edit_faced_related_fossil_po_report(request, faced_related_id, task_id):
    heading = "Section 16: Edit of faced related"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    faced_related = FacedRelatedOperation.objects.get(id=faced_related_id)
    if request.method == 'POST':
        data = request.POST
        challenges = data.get('challenges')
        proposed_solution = data.get('proposed_solution')
        task = Task.objects.get(id=task_id)

        if challenges or proposed_solution:
            faced_related.user_name_id = request.user
            faced_related.challenges = challenges
            faced_related.proposed_solution = proposed_solution
            faced_related.task_id = task
            faced_related.site_id =  current_site
            faced_related.save()
        else:
            return redirect('/po-report/fossil/faced-related-listing/'+str(task_id))
        return redirect('/po-report/fossil/faced-related-listing/'+str(task_id))
    return render(request, 'po_report/fossil/faced_related/edit_faced_related.html', locals())


#--- ---------po-report-rnp--------------

@ login_required(login_url='/login/')
def health_sessions_listing_rnp_po_report(request, task_id):
    heading = "Section 1: Details of transaction of sessions on health & nutrition"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, health_sessions)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/health_sessions/health_sessions_listing.html', locals())

@ login_required(login_url='/login/')
def add_health_sessions_rnp_po_report(request, task_id):
    heading = "Section 1: Add of transaction of sessions on health & nutrition"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, site=current_site)
    fossil_ah_session_category_obj =  FossilAHSessionCategory.objects.filter(status=1)
  
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_selected_id = data.get('awc_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_ah_session_id = data.get('fossil_ah_session')
        fossil_ah_session_selected_id = data.get('fossil_ah_session_category')
        fossil_ah_session = FossilAHSession.objects.get(id=fossil_ah_session_id)
        date_of_session = data.get('date_of_session')
        adolescent_obj =  Adolescent.objects.filter(awc__id=adolescent_selected_id, site=current_site)
        fossil_ah_session_obj =  FossilAHSession.objects.filter(fossil_ah_session_category__id = fossil_ah_session_selected_id)
        session_day = data.get('session_day')
        age = data.get('age')
        gender = data.get('gender')
        facilitator_name = data.get('facilitator_name')
        designations = data.get('designations')
        task = Task.objects.get(id=task_id)
        if AHSession.objects.filter(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
                                    date_of_session=date_of_session,  status=1).exists():
            exist_error = "Please try again this data already exists!!!"
            return render(request,'po_report/rnp/health_sessions/add_health_sessions.html', locals())
        else:
            health_sessions = AHSession.objects.create(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
            date_of_session=date_of_session, session_day=session_day,designation_data = designations,
            age=age, gender=gender, facilitator_name = facilitator_name, task=task, site_id = current_site)
            health_sessions.save()
        return redirect('/po-report/rnp/health-sessions-listing/'+str(task_id))
    return render(request, 'po_report/rnp/health_sessions/add_health_sessions.html', locals())


@ login_required(login_url='/login/')
def edit_health_sessions_rnp_po_report(request, ahsession_id, task_id):
    heading = "Section 1: Edit of transaction of sessions on health & nutrition"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.get(id=ahsession_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id=health_sessions.adolescent_name.awc.id, site=current_site)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    fossil_ah_session_obj =  FossilAHSession.objects.filter(status=1, fossil_ah_session_category__id=health_sessions.fossil_ah_session.fossil_ah_session_category.id)
    fossil_ah_session_category_obj =  FossilAHSessionCategory.objects.filter(status=1,)
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_ah_session_id = data.get('fossil_ah_session')
        fossil_ah_session = FossilAHSession.objects.get(id=fossil_ah_session_id)
        date_of_session = data.get('date_of_session')
        session_day = data.get('session_day')
        age = data.get('age')
        gender = data.get('gender')
        facilitator_name = data.get('facilitator_name')
        designations = data.get('designations')
        task = Task.objects.get(id=task_id)
        if AHSession.objects.filter(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
                                    date_of_session=date_of_session,  status=1).exclude(id=ahsession_id).exists():
            exist_error = "Please try again this data already exists!!!"
            return render(request, 'po_report/rnp/health_sessions/edit_health_sessions.html', locals())
        else:
            health_sessions.adolescent_name_id = adolescent_name
            health_sessions.fossil_ah_session_id = fossil_ah_session
            health_sessions.age = age
            health_sessions.gender = gender
            health_sessions.date_of_session = date_of_session
            health_sessions.session_day = session_day
            health_sessions.designation_data = designations
            health_sessions.facilitator_name = facilitator_name
            health_sessions.task_id = task
            health_sessions.site_id =  current_site
            health_sessions.save()
        return redirect('/po-report/rnp/health-sessions-listing/'+str(task_id))
    return render(request, 'po_report/rnp/health_sessions/edit_health_sessions.html', locals())


@ login_required(login_url='/login/')
def girls_ahwd_listing_rnp_po_report(request, task_id):
    heading = "Section 3(a): Details of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, girls_ahwd)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/girls_ahwd/girls_ahwd_listing.html', locals())


@ login_required(login_url='/login/')
def add_girls_ahwd_rnp_po_report(request, task_id):
    heading = "Section 3(a): Add of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    school_obj = School.objects.filter(status=1, id__in=school_id)
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')

        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        tt_10_14_years = data.get('tt_10_14_years')
        tt_15_19_years = data.get('tt_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        girls_ahwd = GirlsAHWD.objects.create(place_of_ahwd=place_of_ahwd, content_type=content_type, object_id=selected_object_id,
        participated_10_14_years=participated_10_14_years, date_of_ahwd=date_of_ahwd, hwc_name=hwc_name,
        participated_15_19_years=participated_15_19_years, bmi_10_14_years=bmi_10_14_years,
        bmi_15_19_years=bmi_15_19_years, hb_10_14_years=hb_10_14_years, hb_15_19_years=hb_15_19_years,
        tt_10_14_years=tt_10_14_years, tt_15_19_years=tt_15_19_years, counselling_10_14_years=counselling_10_14_years,
        counselling_15_19_years=counselling_15_19_years, referral_10_14_years=referral_10_14_years,
        referral_15_19_years=referral_15_19_years, task=task, site_id = current_site)
        girls_ahwd.save()
        return redirect('/po-report/rnp/girls-ahwd-listing/'+str(task_id))
    return render(request, 'po_report/rnp/girls_ahwd/add_girls_ahwd.html', locals())


@ login_required(login_url='/login/')
def edit_girls_ahwd_rnp_po_report(request, girls_ahwd_id, task_id):
    heading = "Section 3(a): Edit of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.get(id=girls_ahwd_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    school_obj = School.objects.filter(status=1, id__in=school_id)
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        tt_10_14_years = data.get('tt_10_14_years')
        tt_15_19_years = data.get('tt_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        girls_ahwd.place_of_ahwd = place_of_ahwd
        girls_ahwd.content_type = content_type
        girls_ahwd.object_id = selected_object_id
        girls_ahwd.hwc_name = hwc_name
        girls_ahwd.date_of_ahwd = date_of_ahwd
        girls_ahwd.participated_10_14_years = participated_10_14_years
        girls_ahwd.participated_15_19_years = participated_15_19_years
        girls_ahwd.bmi_10_14_years = bmi_10_14_years
        girls_ahwd.bmi_15_19_years = bmi_15_19_years
        girls_ahwd.hb_10_14_years = hb_10_14_years
        girls_ahwd.hb_15_19_years = hb_15_19_years
        girls_ahwd.tt_10_14_years = tt_10_14_years
        girls_ahwd.tt_15_19_years = tt_15_19_years
        girls_ahwd.counselling_10_14_years = counselling_10_14_years
        girls_ahwd.counselling_15_19_years = counselling_15_19_years
        girls_ahwd.referral_10_14_years = referral_10_14_years
        girls_ahwd.referral_15_19_years = referral_15_19_years
        girls_ahwd.task_id = task
        girls_ahwd.site_id =  current_site
        girls_ahwd.save()
        return redirect('/po-report/rnp/girls-ahwd-listing/'+str(task_id))
    return render(request, 'po_report/rnp/girls_ahwd/edit_girls_ahwd.html', locals())




@ login_required(login_url='/login/')
def boys_ahwd_listing_rnp_po_report(request, task_id):
    heading = "Section 3(b): Details of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, boys_ahwd)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/boys_ahwd/boys_ahwd_listing.html', locals())


@ login_required(login_url='/login/')
def add_boys_ahwd_rnp_po_report(request, task_id):
    heading = "Section 3(b): Add of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    school_obj = School.objects.filter(status=1, id__in=school_id)
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        boys_ahwd = BoysAHWD.objects.create(place_of_ahwd=place_of_ahwd, content_type=content_type, object_id=selected_object_id,
        participated_10_14_years=participated_10_14_years, date_of_ahwd=date_of_ahwd, hwc_name=hwc_name,
        participated_15_19_years=participated_15_19_years, bmi_10_14_years=bmi_10_14_years,
        bmi_15_19_years=bmi_15_19_years, hb_10_14_years=hb_10_14_years, hb_15_19_years=hb_15_19_years,
        counselling_10_14_years=counselling_10_14_years,
        counselling_15_19_years=counselling_15_19_years, referral_10_14_years=referral_10_14_years,
        referral_15_19_years=referral_15_19_years, task=task, site_id = current_site)
        boys_ahwd.save()
        return redirect('/po-report/rnp/boys-ahwd-listing/'+str(task_id))
    return render(request, 'po_report/rnp/boys_ahwd/add_boys_ahwd.html', locals())


@ login_required(login_url='/login/')
def edit_boys_ahwd_rnp_po_report(request, boys_ahwd_id, task_id):
    heading = "Section 3(b): Edit of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.get(id=boys_ahwd_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    school_obj = School.objects.filter(status=1, id__in=school_id)
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        boys_ahwd.place_of_ahwd = place_of_ahwd
        boys_ahwd.content_type = content_type
        boys_ahwd.object_id = selected_object_id
        boys_ahwd.hwc_name = hwc_name
        boys_ahwd.date_of_ahwd = date_of_ahwd
        boys_ahwd.participated_10_14_years = participated_10_14_years
        boys_ahwd.participated_15_19_years = participated_15_19_years
        boys_ahwd.bmi_10_14_years = bmi_10_14_years
        boys_ahwd.bmi_15_19_years = bmi_15_19_years
        boys_ahwd.hb_10_14_years = hb_10_14_years
        boys_ahwd.hb_15_19_years = hb_15_19_years
        boys_ahwd.counselling_10_14_years = counselling_10_14_years
        boys_ahwd.counselling_15_19_years = counselling_15_19_years
        boys_ahwd.referral_10_14_years = referral_10_14_years
        boys_ahwd.referral_15_19_years = referral_15_19_years
        boys_ahwd.task_id = task
        boys_ahwd.site_id =  current_site
        boys_ahwd.save()
        return redirect('/po-report/rnp/boys-ahwd-listing/'+str(task_id))
    return render(request, 'po_report/rnp/boys_ahwd/edit_boys_ahwd.html', locals())



@ login_required(login_url='/login/')
def vocation_listing_rnp_po_report(request, task_id):
    heading = "Section 2: Details of adolescent boys linked with vocational training & placement"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, vocation_obj)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/voctional_training/vocation_listing.html', locals())

@ login_required(login_url='/login/')
def add_vocation_rnp_po_report(request, task_id):
    heading = "Section 2: Add of adolescent boys linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.filter()
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    tranining_sub_obj = TrainingSubject.objects.all()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id=training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)
        vocation_obj = AdolescentVocationalTraining.objects.create(adolescent_name=adolescent_name, date_of_registration=date_of_registration, 
        age=age or None, parent_guardian_name=parent_guardian_name, training_subject=training_subject,
        training_providing_by=training_providing_by, duration_days=duration_days, training_complated=training_complated, 
        placement_offered=placement_offered or None, placement_accepted=placement_accepted or None, type_of_employment=type_of_employment or None,
        task=task, site_id = current_site)

        vocation_obj.save()
        return redirect('/po-report/rnp/vocation-listing/'+str(task_id))
    return render(request, 'po_report/rnp/voctional_training/add_vocation_training.html', locals())


@ login_required(login_url='/login/')
def edit_vocation_rnp_po_report(request, vocation_id, task_id):
    heading = "Section 2: Edit of adolescent boys linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.get(id=vocation_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    tranining_sub_obj = TrainingSubject.objects.all()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id = training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)
       

        vocation_obj.adolescent_name_id = adolescent_name
        vocation_obj.date_of_registration = date_of_registration
        vocation_obj.age = age or None
        vocation_obj.parent_guardian_name = parent_guardian_name
        vocation_obj.training_subject = training_subject
        vocation_obj.training_providing_by = training_providing_by
        vocation_obj.duration_days = duration_days
        vocation_obj.training_complated = training_complated
        vocation_obj.placement_offered = placement_offered or None
        vocation_obj.placement_accepted = placement_accepted or None
        vocation_obj.type_of_employment = type_of_employment or None
        vocation_obj.task_id = task
        vocation_obj.site_id =  current_site
        vocation_obj.save()
        return redirect('/po-report/rnp/vocation-listing/'+str(task_id))
    return render(request, 'po_report/rnp/voctional_training/edit_vocation_training.html', locals())



@ login_required(login_url='/login/')
def adolescents_referred_listing_rnp_po_report(request, task_id):
    heading = "Section 4: Details of adolescents referred"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.filter(status=1, awc_name__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, adolescents_referred)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/adolescent_referred/adolescent_referred_listing.html', locals())

@ login_required(login_url='/login/')
def add_adolescents_referred_rnp_po_report(request, task_id):
    heading = "Section 4: Add of adolescents referred"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.filter()
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_referred_10_14_year = data.get('girls_referred_10_14_year')
        girls_referred_15_19_year = data.get('girls_referred_15_19_year')
        boys_referred_10_14_year = data.get('boys_referred_10_14_year')
        boys_referred_15_19_year = data.get('boys_referred_15_19_year')
        girls_hwc_referred = data.get('girls_hwc_referred')
        girls_hwc_visited = data.get('girls_hwc_visited')
        girls_afhc_referred = data.get('girls_afhc_referred')
        girls_afhc_visited = data.get('girls_afhc_visited')
        girls_dh_referred = data.get('girls_dh_referred')
        girls_dh_visited = data.get('girls_dh_visited')
        boys_hwc_referred = data.get('boys_hwc_referred')
        boys_hwc_visited = data.get('boys_hwc_visited')
        boys_afhc_referred = data.get('boys_afhc_referred')
        boys_afhc_visited = data.get('boys_afhc_visited')
        boys_dh_referred = data.get('boys_dh_referred')
        boys_dh_visited = data.get('boys_dh_visited')
        task = Task.objects.get(id=task_id)
        adolescents_referred = AdolescentsReferred.objects.create(awc_name=awc_name, girls_referred_10_14_year=girls_referred_10_14_year, 
        girls_referred_15_19_year=girls_referred_15_19_year, boys_referred_10_14_year=boys_referred_10_14_year, boys_referred_15_19_year=boys_referred_15_19_year,
        girls_hwc_referred=girls_hwc_referred, girls_hwc_visited=girls_hwc_visited, girls_afhc_referred=girls_afhc_referred, girls_afhc_visited=girls_afhc_visited,
        girls_dh_referred=girls_dh_referred, girls_dh_visited=girls_dh_visited, boys_hwc_referred=boys_hwc_referred, boys_hwc_visited=boys_hwc_visited,
        boys_afhc_referred=boys_afhc_referred, boys_afhc_visited=boys_afhc_visited, 
        boys_dh_referred=boys_dh_referred, boys_dh_visited=boys_dh_visited, task=task, site_id = current_site)
        adolescents_referred.save()
        return redirect('/po-report/rnp/adolescent-referred-listing/'+str(task_id))
    return render(request, 'po_report/rnp/adolescent_referred/add_adolescen_referred.html', locals())


@ login_required(login_url='/login/')
def edit_adolescents_referred_rnp_po_report(request, adolescents_referred_id, task_id):
    heading = "Section 4: Edit of adolescents referred"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.get(id=adolescents_referred_id)
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_referred_10_14_year = data.get('girls_referred_10_14_year')
        girls_referred_15_19_year = data.get('girls_referred_15_19_year')
        boys_referred_10_14_year = data.get('boys_referred_10_14_year')
        boys_referred_15_19_year = data.get('boys_referred_15_19_year')
        girls_hwc_referred = data.get('girls_hwc_referred')
        girls_hwc_visited = data.get('girls_hwc_visited')
        girls_afhc_referred = data.get('girls_afhc_referred')
        girls_afhc_visited = data.get('girls_afhc_visited')
        girls_dh_referred = data.get('girls_dh_referred')
        girls_dh_visited = data.get('girls_dh_visited')
        boys_hwc_referred = data.get('boys_hwc_referred')
        boys_hwc_visited = data.get('boys_hwc_visited')
        boys_afhc_referred = data.get('boys_afhc_referred')
        boys_afhc_visited = data.get('boys_afhc_visited')
        boys_dh_referred = data.get('boys_dh_referred')
        boys_dh_visited = data.get('boys_dh_visited')  
        task = Task.objects.get(id=task_id)

        adolescents_referred.awc_name_id = awc_name
        adolescents_referred.girls_referred_10_14_year = girls_referred_10_14_year
        adolescents_referred.girls_referred_15_19_year = girls_referred_15_19_year
        adolescents_referred.boys_referred_10_14_year = boys_referred_10_14_year
        adolescents_referred.boys_referred_15_19_year = boys_referred_15_19_year
        adolescents_referred.girls_hwc_referred = girls_hwc_referred
        adolescents_referred.girls_hwc_visited = girls_hwc_visited
        adolescents_referred.girls_afhc_referred = girls_afhc_referred
        adolescents_referred.girls_afhc_visited = girls_afhc_visited
        adolescents_referred.girls_dh_referred = girls_dh_referred
        adolescents_referred.girls_dh_visited = girls_dh_visited
        adolescents_referred.boys_hwc_referred = boys_hwc_referred
        adolescents_referred.boys_hwc_visited = boys_hwc_visited
        adolescents_referred.boys_afhc_referred = boys_afhc_referred
        adolescents_referred.boys_afhc_visited = boys_afhc_visited
        adolescents_referred.boys_dh_referred = boys_dh_referred
        adolescents_referred.boys_dh_visited = boys_dh_visited
        adolescents_referred.task_id = task
        adolescents_referred.site_id =  current_site
        adolescents_referred.save()
        return redirect('/po-report/rnp/adolescent-referred-listing/'+str(task_id))
    return render(request, 'po_report/rnp/adolescent_referred/edit_adolescent_referred.html', locals())



@ login_required(login_url='/login/')
def friendly_club_listing_rnp_po_report(request, task_id):
    heading = "Section 5: Details of Adolescent Friendly Club (AFC)"
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(status=1, panchayat_name__id__in=panchayat_id, task__id = task_id)
    data = pagination_function(request, friendly_club)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/friendly_club/friendly_club_listing.html', locals())

@ login_required(login_url='/login/')
def add_friendly_club_rnp_po_report(request, task_id):
    heading = "Section 5: Add of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(status=1)
    gramapanchayat = GramaPanchayat.objects.filter(status=1, id__in=panchayat_id)
    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        panchayat_name_id = data.get('panchayat_name')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)

        friendly_club = AdolescentFriendlyClub.objects.create(start_date = date_of_registration, panchayat_name=panchayat_name,
        hsc_name=hsc_name, subject=subject, facilitator=facilitator, designation=designation,
        no_of_sahiya=no_of_sahiya, no_of_aww=no_of_aww, pe_girls_10_14_year=pe_girls_10_14_year,
        pe_girls_15_19_year=pe_girls_15_19_year, pe_boys_10_14_year=pe_boys_10_14_year,
        pe_boys_15_19_year=pe_boys_15_19_year, task=task, site_id = current_site)
        friendly_club.save()
        return redirect('/po-report/rnp/friendly-club-listing/'+str(task_id))
    return render(request, 'po_report/rnp/friendly_club/add_friendly_club.html', locals())



@ login_required(login_url='/login/')
def edit_friendly_club_rnp_po_report(request, friendly_club_id, task_id):
    heading = "Section 5: Edit of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.get(id=friendly_club_id)
    gramapanchayat = GramaPanchayat.objects.filter(status=1, id__in=panchayat_id)
    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        panchayat_name_id = data.get('panchayat_name')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)

        friendly_club.start_date = date_of_registration
        friendly_club.panchayat_name_id = panchayat_name
        friendly_club.hsc_name = hsc_name
        friendly_club.subject = subject
        friendly_club.facilitator = facilitator
        friendly_club.designation = designation
        friendly_club.no_of_sahiya = no_of_sahiya
        friendly_club.no_of_aww = no_of_aww
        friendly_club.pe_girls_10_14_year = pe_girls_10_14_year
        friendly_club.pe_girls_15_19_year = pe_girls_15_19_year
        friendly_club.pe_boys_10_14_year = pe_boys_10_14_year
        friendly_club.pe_boys_15_19_year = pe_boys_15_19_year
        friendly_club.task_id = task
        friendly_club.site_id =  current_site
        friendly_club.save()
        return redirect('/po-report/rnp/friendly-club-listing/'+str(task_id))
    return render(request, 'po_report/rnp/friendly_club/edit_friendly_club.html', locals())



@ login_required(login_url='/login/')
def balsansad_meeting_listing_rnp_po_report(request, task_id):
    heading = "Section 6: Details of Bal Sansad meetings conducted"
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.filter(status=1, school_name__id__in=school_id, task__id = task_id)
    data = pagination_function(request, balsansad_meeting)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/bal_sansad_metting/bal_sansad_listing.html', locals())

@ login_required(login_url='/login/')
def add_balsansad_meeting_rnp_po_report(request, task_id):
    heading = "Section 6: Add of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.filter()
    school = School.objects.filter(status=1, id__in=school_id)
    masterlookups_issues_discussion = MasterLookUp.objects.filter(parent__slug = 'issues_discussion')

    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        school_name_id = data.get('school_name')
        school_name = School.objects.get(id=school_name_id)
        no_of_participants = data.get('no_of_participants')
        decision_taken = data.get('decision_taken')
        issues_discussion = data.get('issues_discussion')
        task = Task.objects.get(id=task_id)
        balsansad_meeting = BalSansadMeeting.objects.create(start_date = date_of_registration, school_name=school_name,
        no_of_participants=no_of_participants, decision_taken=decision_taken,
        task=task, site_id = current_site)
        if issues_discussion:
            issues_discussion = MasterLookUp.objects.get(id=issues_discussion)
            balsansad_meeting.issues_discussion = issues_discussion
        balsansad_meeting.save()
        return redirect('/po-report/rnp/balsansad-listing/'+str(task_id))
    return render(request, 'po_report/rnp/bal_sansad_metting/add_bal_sansad.html', locals())


@ login_required(login_url='/login/')
def edit_balsansad_meeting_rnp_po_report(request, balsansad_id, task_id):
    heading = "Section 6: Edit of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.get(id=balsansad_id)
    school = School.objects.filter(status=1, id__in=school_id)
    masterlookups_issues_discussion = MasterLookUp.objects.filter(parent__slug = 'issues_discussion')

    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        school_name_id = data.get('school_name')
        school_name = School.objects.get(id=school_name_id)
        no_of_participants = data.get('no_of_participants')
        decision_taken = data.get('decision_taken')
        issues_discussion = data.get('issues_discussion')
        task = Task.objects.get(id=task_id)
        balsansad_meeting.start_date = date_of_registration
        balsansad_meeting.school_name_id = school_name
        balsansad_meeting.no_of_participants = no_of_participants
        balsansad_meeting.decision_taken = decision_taken
        balsansad_meeting.task_id = task
        balsansad_meeting.site_id =  current_site
        if issues_discussion:
            issues_discussion = MasterLookUp.objects.get(id=issues_discussion)
            balsansad_meeting.issues_discussion = issues_discussion
        balsansad_meeting.save()
        return redirect('/po-report/rnp/balsansad-listing/'+str(task_id))
    return render(request, 'po_report/rnp/bal_sansad_metting/edit_bal_sansad.html', locals())


@ login_required(login_url='/login/')
def community_activities_listing_rnp_po_report(request, task_id):
    heading = "Section 7: Details of community engagement activities"
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.filter(status=1, village_name__id__in=village_id, task__id = task_id)
    data = pagination_function(request, activities)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/community_activities/community_activities_listing.html', locals())


@ login_required(login_url='/login/')
def add_community_activities_rnp_po_report(request, task_id):
    heading = "Section 7: Add of community engagement activities"
    current_site = request.session.get('site_id')
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.filter(status=1,)
    village =  Village.objects.filter(status=1, id__in=village_id)
    masterlookups_event = MasterLookUp.objects.filter(parent__slug = 'event')
    masterlookups_activity = MasterLookUp.objects.filter(parent__slug = 'activities')

    if request.method == 'POST':
        data = request.POST
        village_name_id = data.get('village_name')
        date_of_registration = data.get('date_of_registration')
        village_name = Village.objects.get(id=village_name_id)
        name_of_event_activity = data.get('name_of_event_activity')
        name_of_event_id = data.get('name_of_event')
        name_of_activity_id = data.get('name_of_activity')
        organized_by = data.get('organized_by')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)

        activities =  CommunityEngagementActivities.objects.create(village_name=village_name, start_date = date_of_registration,
        name_of_event_activity=name_of_event_activity, organized_by=organized_by,
        girls_10_14_year=girls_10_14_year, girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year,
        boys_15_19_year=boys_15_19_year, champions_15_19_year=champions_15_19_year, adult_male=adult_male,
        adult_female=adult_female, teachers=teachers, pri_members=pri_members, services_providers=services_providers,
        sms_members=sms_members, other=other, task=task, site_id = current_site)
        
        if name_of_event_id:
            name_of_event = MasterLookUp.objects.get(id = name_of_event_id)
            activities.event_name = name_of_event

        if name_of_activity_id:
            name_of_activity = MasterLookUp.objects.get(id = name_of_activity_id)
            activities.activity_name = name_of_activity
        activities.save()
        return redirect('/po-report/rnp/community-activities-listing/'+str(task_id))
    return render(request, 'po_report/rnp/community_activities/add_community_activities.html', locals())


@ login_required(login_url='/login/')
def edit_community_activities_rnp_po_report(request, activities_id, task_id):
    heading = "Section 7: Edit of community engagement activities"
    current_site = request.session.get('site_id')
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.get(id=activities_id)
    village =  Village.objects.filter(status=1, id__in=village_id)
    masterlookups_event = MasterLookUp.objects.filter(parent__slug = 'event')
    masterlookups_activity = MasterLookUp.objects.filter(parent__slug = 'activities')

    if request.method == 'POST':
        data = request.POST
        village_name_id = data.get('village_name')
        date_of_registration = data.get('date_of_registration')
        village_name = Village.objects.get(id=village_name_id)
        name_of_event_activity = data.get('name_of_event_activity')
        # theme_topic = data.get('theme_topic')
        name_of_event_id = data.get('name_of_event')
        name_of_activity_id = data.get('name_of_activity')

        organized_by = data.get('organized_by')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)

        activities.start_date = date_of_registration
        activities.village_name_id = village_name
        activities.name_of_event_activity = name_of_event_activity
        # activities.theme_topic = theme_topic
        activities.organized_by = organized_by
        activities.boys_10_14_year = boys_10_14_year
        activities.boys_15_19_year = boys_15_19_year
        activities.girls_10_14_year = girls_10_14_year
        activities.girls_15_19_year = girls_15_19_year
        activities.champions_15_19_year = champions_15_19_year
        activities.adult_male = adult_male
        activities.adult_female = adult_female
        activities.teachers = teachers
        activities.pri_members = pri_members
        activities.services_providers = services_providers
        activities.sms_members = sms_members
        activities.other = other
        activities.task_id = task
        activities.site_id =  current_site
        
        if name_of_event_id:
            name_of_event = MasterLookUp.objects.get(id = name_of_event_id)
            activities.event_name = name_of_event

        if name_of_activity_id:
            name_of_activity = MasterLookUp.objects.get(id = name_of_activity_id)
            activities.activity_name = name_of_activity
        activities.save()
        return redirect('/po-report/rnp/community-activities-listing/'+str(task_id))
    return render(request, 'po_report/rnp/community_activities/edit_community_activities.html', locals())


@ login_required(login_url='/login/')
def champions_listing_rnp_po_report(request, task_id):
    heading = "Section 8: Details of exposure visits of adolescent champions"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.filter(status=1, awc_name__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, champions)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/champions/champions_listing.html', locals())




@ login_required(login_url='/login/')
def add_champions_rnp_po_report(request, task_id):
    heading = "Section 8: Add of exposure visits of adolescent champions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.filter()
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        date_of_visit = data.get('date_of_visit')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        first_inst_visited = data.get('first_inst_visited')
        second_inst_visited = data.get('second_inst_visited')
        third_inst_visited = data.get('third_inst_visited')
        fourth_inst_visited = data.get('fourth_inst_visited')
        task = Task.objects.get(id=task_id)

        champions =  Champions.objects.create(awc_name=awc_name, date_of_visit=date_of_visit, girls_10_14_year=girls_10_14_year,
        girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year, boys_15_19_year=boys_15_19_year,
        first_inst_visited=first_inst_visited,second_inst_visited=second_inst_visited or None,
        third_inst_visited=third_inst_visited or None, fourth_inst_visited=fourth_inst_visited or None, task=task, site_id = current_site)
        champions.save()
        return redirect('/po-report/rnp/champions-listing/'+str(task_id))
    return render(request, 'po_report/rnp/champions/add_champions.html', locals())


@ login_required(login_url='/login/')
def edit_champions_rnp_po_report(request, champions_id, task_id):
    heading = "Section 8: Edit of exposure visits of adolescent champions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.get(id=champions_id)
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        date_of_visit = data.get('date_of_visit')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        first_inst_visited = data.get('first_inst_visited')
        second_inst_visited = data.get('second_inst_visited')
        third_inst_visited = data.get('third_inst_visited')
        fourth_inst_visited = data.get('fourth_inst_visited')
        task = Task.objects.get(id=task_id)

        champions.awc_name_id = awc_name       
        champions.date_of_visit = date_of_visit 
        champions.girls_10_14_year = girls_10_14_year       
        champions.girls_15_19_year = girls_15_19_year     
        champions.boys_10_14_year = boys_10_14_year       
        champions.boys_15_19_year = boys_15_19_year       
        champions.first_inst_visited = first_inst_visited
        champions.second_inst_visited= second_inst_visited or None
        champions.third_inst_visited = third_inst_visited or None
        champions.fourth_inst_visited = fourth_inst_visited or None
        champions.task_id = task
        champions.site_id =  current_site        
        champions.save()
        return redirect('/po-report/rnp/champions-listing/'+str(task_id))
    return render(request, 'po_report/rnp/champions/edit_champions.html', locals())

@ login_required(login_url='/login/')
def reenrolled_listing_rnp_po_report(request, task_id):
    heading = "Section 9: Details of adolescent re-enrolled in schools"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, adolescent_reenrolled)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/re_enrolled/re_enrolled_listing.html', locals())

@ login_required(login_url='/login/')
def add_reenrolled_rnp_po_report(request, task_id):
    heading = "Section 9: Add of adolescent re-enrolled in schools"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter()
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    # school = School.objects.filter(status=1, id__in = school_id)
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        gender = data.get('gender')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        school_name = data.get('school_name')
        # school_name = School.objects.get(id=school_name_id)
        which_class_enrolled = data.get('which_class_enrolled')
        task = Task.objects.get(id=task_id)

        adolescent_reenrolled =  AdolescentRe_enrolled.objects.create(adolescent_name=adolescent_name,
        gender=gender, age=age, parent_guardian_name=parent_guardian_name, school_name=school_name, which_class_enrolled=which_class_enrolled,
        task=task, site_id = current_site)
        adolescent_reenrolled.save()
        return redirect('/po-report/rnp/reenrolled-listing/'+str(task_id))
    return render(request, 'po_report/rnp/re_enrolled/add_re_enrolled.html', locals())


@ login_required(login_url='/login/')
def edit_reenrolled_rnp_po_report(request, reenrolled_id, task_id):
    heading = "Section 9: Edit of adolescent re-enrolled in schools"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.get(id=reenrolled_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    # school = School.objects.filter()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        gender = data.get('gender')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        school_name = data.get('school_name')
        # school_name = School.objects.get(id=school_name_id)
        which_class_enrolled = data.get('which_class_enrolled')
        task = Task.objects.get(id=task_id)

        adolescent_reenrolled.adolescent_name_id = adolescent_name
        adolescent_reenrolled.gender = gender
        adolescent_reenrolled.age = age
        adolescent_reenrolled.parent_guardian_name = parent_guardian_name
        adolescent_reenrolled.school_name = school_name
        adolescent_reenrolled.which_class_enrolled = which_class_enrolled
        adolescent_reenrolled.task_id = task
        adolescent_reenrolled.site_id =  current_site
        adolescent_reenrolled.save()
        return redirect('/po-report/rnp/reenrolled-listing/'+str(task_id))
    return render(request, 'po_report/rnp/re_enrolled/edit_re_enrolled.html', locals())


@ login_required(login_url='/login/')
def stakeholders_listing_rnp_po_report(request, task_id):
    heading = "Section 10: Details of capacity building of different stakeholders"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    if Stakeholder.objects.filter(task=task_id).exists():
        error="disabled"
    stakeholders_obj = Stakeholder.objects.filter(user_name=request.user.id, task__id = task_id)
    data = pagination_function(request, stakeholders_obj)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/stakeholders/stakeholders_listing.html', locals())


@ login_required(login_url='/login/')
def add_stakeholders_rnp_po_report(request, task_id):
    heading = "Section 10: Add of capacity building of different stakeholders"
    current_site = request.session.get('site_id')
    stakeholders_obj = Stakeholder.objects.filter()
    if request.method == 'POST':
        data = request.POST
        master_trainers_male = data.get('master_trainers_male')
        master_trainers_female = data.get('master_trainers_female')
        master_trainers_total = data.get('master_trainers_total')
        nodal_teachers_male = data.get('nodal_teachers_male')
        nodal_teachers_female = data.get('nodal_teachers_female')
        nodal_teachers_total = data.get('nodal_teachers_total')
        principals_male = data.get('principals_male')
        principals_female = data.get('principals_female')
        principals_total = data.get('principals_total')
        district_level_officials_male = data.get('district_level_officials_male')
        district_level_officials_female = data.get('district_level_officials_female')
        district_level_officials_total = data.get('district_level_officials_total')
        peer_educator_male = data.get('peer_educator_male')
        peer_educator_female = data.get('peer_educator_female')
        peer_educator_total = data.get('peer_educator_total')
        state_level_officials_male = data.get('state_level_officials_male')
        state_level_officials_female = data.get('state_level_officials_female')
        state_level_officials_total = data.get('state_level_officials_total')
        icds_awws_male = data.get('icds_awws_male')
        icds_awws_female = data.get('icds_awws_female')
        icds_awws_total = data.get('icds_awws_total')
        icds_supervisors_male = data.get('icds_supervisors_male')
        icds_supervisors_female = data.get('icds_supervisors_female')
        icds_supervisors_total = data.get('icds_supervisors_total')
        icds_peer_educator_male = data.get('icds_peer_educator_male')
        icds_peer_educator_female = data.get('icds_peer_educator_female')
        icds_peer_educator_total = data.get('icds_peer_educator_total')
        icds_child_developement_project_officers_male = data.get('icds_child_developement_project_officers_male')
        icds_child_developement_project_officers_female = data.get('icds_child_developement_project_officers_female')
        icds_child_developement_project_officers_total = data.get('icds_child_developement_project_officers_total')
        icds_district_level_officials_male = data.get('icds_district_level_officials_male')
        icds_district_level_officials_female = data.get('icds_district_level_officials_female')
        icds_district_level_officials_total = data.get('icds_district_level_officials_total')
        icds_state_level_officials_male = data.get('icds_state_level_officials_male')
        icds_state_level_officials_female = data.get('icds_state_level_officials_female')
        icds_state_level_officials_total = data.get('icds_state_level_officials_total')
        health_ashas_male = data.get('health_ashas_male')
        health_ashas_female = data.get('health_ashas_female')
        health_ashas_total = data.get('health_ashas_total')
        health_anms_male = data.get('health_anms_male')
        health_anms_female = data.get('health_anms_female')
        health_anms_total = data.get('health_anms_total')
        health_bpm_bhm_pheos_male = data.get('health_bpm_bhm_pheos_male')
        health_bpm_bhm_pheos_female = data.get('health_bpm_bhm_pheos_female')
        health_bpm_bhm_pheos_total = data.get('health_bpm_bhm_pheos_total')
        health_medical_officers_male = data.get('health_medical_officers_male')
        health_medical_officers_female = data.get('health_medical_officers_female')
        health_medical_officers_total = data.get('health_medical_officers_total')
        health_district_level_officials_male = data.get('health_district_level_officials_male')
        health_district_level_officials_female = data.get('health_district_level_officials_female')
        health_district_level_officials_total = data.get('health_district_level_officials_total')
        health_state_level_officials_male = data.get('health_state_level_officials_male')
        health_state_level_officials_female = data.get('health_state_level_officials_female')
        health_state_level_officials_total = data.get('health_state_level_officials_total')
        health_rsk_male = data.get('health_rsk_male')
        health_rsk_female = data.get('health_rsk_female')
        health_rsk_total = data.get('health_rsk_total')
        health_peer_educator_male = data.get('health_peer_educator_male')
        health_peer_educator_female = data.get('health_peer_educator_female')
        health_peer_educator_total = data.get('health_peer_educator_total')
        panchayat_ward_members_male = data.get('panchayat_ward_members_male')
        panchayat_ward_members_female = data.get('panchayat_ward_members_female')
        panchayat_ward_members_total = data.get('panchayat_ward_members_total')
        panchayat_up_mukhiya_up_Pramukh_male = data.get('panchayat_up_mukhiya_up_Pramukh_male')
        panchayat_up_mukhiya_up_Pramukh_female = data.get('panchayat_up_mukhiya_up_Pramukh_female')
        panchayat_up_mukhiya_up_Pramukh_total = data.get('panchayat_up_mukhiya_up_Pramukh_total')
        panchayat_mukhiya_Pramukh_male = data.get('panchayat_mukhiya_Pramukh_male')
        panchayat_mukhiya_Pramukh_female = data.get('panchayat_mukhiya_Pramukh_female')
        panchayat_mukhiya_Pramukh_total = data.get('panchayat_mukhiya_Pramukh_total')
        panchayat_samiti_member_male = data.get('panchayat_samiti_member_male')
        panchayat_samiti_member_female = data.get('panchayat_samiti_member_female')
        panchayat_samiti_member_total = data.get('panchayat_samiti_member_total')
        panchayat_zila_parishad_member_male = data.get('panchayat_zila_parishad_member_male')
        panchayat_zila_parishad_member_female = data.get('panchayat_zila_parishad_member_female')
        panchayat_zila_parishad_member_total = data.get('panchayat_zila_parishad_member_total')
        panchayat_vc_zila_parishad_male = data.get('panchayat_vc_zila_parishad_male')
        panchayat_vc_zila_parishad_female = data.get('panchayat_vc_zila_parishad_female')
        panchayat_vc_zila_parishad_total = data.get('panchayat_vc_zila_parishad_total')
        panchayat_chairman_zila_parishad_male = data.get('panchayat_chairman_zila_parishad_male')
        panchayat_chairman_zila_parishad_female = data.get('panchayat_chairman_zila_parishad_female')
        panchayat_chairman_zila_parishad_total = data.get('panchayat_chairman_zila_parishad_total')
        panchayat_block_level_officials_male = data.get('panchayat_block_level_officials_male')
        panchayat_block_level_officials_female = data.get('panchayat_block_level_officials_female')
        panchayat_block_level_officials_total = data.get('panchayat_block_level_officials_total')
        panchayat_district_level_officials_male = data.get('panchayat_district_level_officials_male')
        panchayat_district_level_officials_female = data.get('panchayat_district_level_officials_female')
        panchayat_district_level_officials_total = data.get('panchayat_district_level_officials_total')
        panchayat_state_level_officials_male = data.get('panchayat_state_level_officials_male')
        panchayat_state_level_officials_female = data.get('panchayat_state_level_officials_female')
        panchayat_state_level_officials_total = data.get('panchayat_state_level_officials_total')
        media_interns_male = data.get('media_interns_male')
        media_interns_female = data.get('media_interns_female')
        media_interns_total = data.get('media_interns_total')
        media_journalists_male = data.get('media_journalists_male')
        media_journalists_female = data.get('media_journalists_female')
        media_journalists_total = data.get('media_journalists_total')
        media_editors_male = data.get('media_editors_male')
        media_editors_female = data.get('media_editors_female')
        media_editors_total = data.get('media_editors_total')
        others_block_cluster_field_corrdinators_male = data.get('others_block_cluster_field_corrdinators_male')
        others_block_cluster_field_corrdinators_female = data.get('others_block_cluster_field_corrdinators_female')
        others_block_cluster_field_corrdinators_total = data.get('others_block_cluster_field_corrdinators_total')
        others_ngo_staff_corrdinators_male = data.get('others_ngo_staff_corrdinators_male')
        others_ngo_staff_corrdinators_female = data.get('others_ngo_staff_corrdinators_female')
        others_ngo_staff_corrdinators_total = data.get('others_ngo_staff_corrdinators_total')
        others_male = data.get('others_male')
        others_female = data.get('others_female')
        others_total = data.get('others_total')
        total_male = data.get('total_male')
        total_female = data.get('total_female')
        total = data.get('total')
        task = Task.objects.get(id=task_id)
        if total and int(total) != 0:
            stakeholders_obj = Stakeholder.objects.create(user_name=request.user,
            master_trainers_male=master_trainers_male or None, master_trainers_female=master_trainers_female or None, master_trainers_total=master_trainers_total or None,
            nodal_teachers_male=nodal_teachers_male or None, nodal_teachers_female=nodal_teachers_female or None, nodal_teachers_total=nodal_teachers_total or None,
            principals_male=principals_male or None, principals_female=principals_female or None, principals_total=principals_total or None, 
            district_level_officials_male=district_level_officials_male or None, district_level_officials_female=district_level_officials_female or None, district_level_officials_total=district_level_officials_total or None,
            peer_educator_male=peer_educator_male or None, peer_educator_female=peer_educator_female or None, peer_educator_total=peer_educator_total or None,
            state_level_officials_male=state_level_officials_male or None, state_level_officials_female=state_level_officials_female or None, state_level_officials_total=state_level_officials_total or None,
            icds_awws_male=icds_awws_male or None, icds_awws_female=icds_awws_female or None, icds_awws_total=icds_awws_total or None,
            icds_supervisors_male=icds_supervisors_male or None, icds_supervisors_female=icds_supervisors_female or None, icds_supervisors_total=icds_supervisors_total or None,
            icds_peer_educator_male=icds_peer_educator_male or None, icds_peer_educator_female=icds_peer_educator_female or None, icds_peer_educator_total=icds_peer_educator_total or None,
            icds_child_developement_project_officers_male=icds_child_developement_project_officers_male or None, icds_child_developement_project_officers_female=icds_child_developement_project_officers_female or None, icds_child_developement_project_officers_total=icds_child_developement_project_officers_total or None,
            icds_district_level_officials_male=icds_district_level_officials_male or None, icds_district_level_officials_female=icds_district_level_officials_female or None, icds_district_level_officials_total=icds_district_level_officials_total or None,
            icds_state_level_officials_male=icds_state_level_officials_male or None, icds_state_level_officials_female=icds_state_level_officials_female or None, icds_state_level_officials_total=icds_state_level_officials_total or None,
            health_ashas_male=health_ashas_male or None, health_ashas_female=health_ashas_female or None, health_ashas_total=health_ashas_total or None,
            health_anms_male=health_anms_male or None, health_anms_female=health_anms_female or None, health_anms_total=health_anms_total or None,
            health_bpm_bhm_pheos_male=health_bpm_bhm_pheos_male or None, health_bpm_bhm_pheos_female=health_bpm_bhm_pheos_female or None, health_bpm_bhm_pheos_total=health_bpm_bhm_pheos_total or None,
            health_medical_officers_male=health_medical_officers_male or None, health_medical_officers_female=health_medical_officers_female or None, health_medical_officers_total=health_medical_officers_total or None,
            health_district_level_officials_male=health_district_level_officials_male or None, health_district_level_officials_female=health_district_level_officials_female or None, health_district_level_officials_total=health_district_level_officials_total or None,
            health_state_level_officials_male=health_state_level_officials_male or None, health_state_level_officials_female=health_state_level_officials_female or None, health_state_level_officials_total=health_state_level_officials_total or None,
            health_rsk_male=health_rsk_male or None, health_rsk_female=health_rsk_female or None, health_rsk_total=health_rsk_total or None,
            health_peer_educator_male=health_peer_educator_male or None, health_peer_educator_female=health_peer_educator_female or None, health_peer_educator_total=health_peer_educator_total or None,
            panchayat_ward_members_male=panchayat_ward_members_male or None, panchayat_ward_members_female=panchayat_ward_members_female or None, panchayat_ward_members_total=panchayat_ward_members_total or None,
            panchayat_up_mukhiya_up_Pramukh_male=panchayat_up_mukhiya_up_Pramukh_male or None, panchayat_up_mukhiya_up_Pramukh_female=panchayat_up_mukhiya_up_Pramukh_female or None, panchayat_up_mukhiya_up_Pramukh_total=panchayat_up_mukhiya_up_Pramukh_total or None,
            panchayat_mukhiya_Pramukh_male=panchayat_mukhiya_Pramukh_male or None, panchayat_mukhiya_Pramukh_female=panchayat_mukhiya_Pramukh_female or None, panchayat_mukhiya_Pramukh_total=panchayat_mukhiya_Pramukh_total or None,
            panchayat_samiti_member_male=panchayat_samiti_member_male or None, panchayat_samiti_member_female=panchayat_samiti_member_female or None, panchayat_samiti_member_total=panchayat_samiti_member_total or None,
            panchayat_zila_parishad_member_male=panchayat_zila_parishad_member_male or None, panchayat_zila_parishad_member_female=panchayat_zila_parishad_member_female or None, panchayat_zila_parishad_member_total=panchayat_zila_parishad_member_total or None,
            panchayat_vc_zila_parishad_male=panchayat_vc_zila_parishad_male or None, panchayat_vc_zila_parishad_female=panchayat_vc_zila_parishad_female or None, panchayat_vc_zila_parishad_total=panchayat_vc_zila_parishad_total or None,
            panchayat_chairman_zila_parishad_male=panchayat_chairman_zila_parishad_male or None, panchayat_chairman_zila_parishad_female=panchayat_chairman_zila_parishad_female or None, panchayat_chairman_zila_parishad_total=panchayat_chairman_zila_parishad_total or None,
            panchayat_block_level_officials_male=panchayat_block_level_officials_male or None, panchayat_block_level_officials_female=panchayat_block_level_officials_female or None, panchayat_block_level_officials_total=panchayat_block_level_officials_total or None,
            panchayat_district_level_officials_male=panchayat_district_level_officials_male or None, panchayat_district_level_officials_female=panchayat_district_level_officials_female or None, panchayat_district_level_officials_total=panchayat_district_level_officials_total or None,
            panchayat_state_level_officials_male=panchayat_state_level_officials_male or None, panchayat_state_level_officials_female=panchayat_state_level_officials_female or None, panchayat_state_level_officials_total=panchayat_state_level_officials_total or None,
            media_interns_male=media_interns_male or None, media_interns_female=media_interns_female or None, media_interns_total=media_interns_total or None,
            media_journalists_male=media_journalists_male or None, media_journalists_female=media_journalists_female or None, media_journalists_total=media_journalists_total or None,
            media_editors_male=media_editors_male or None, media_editors_female=media_editors_female or None, media_editors_total=media_editors_total or None,
            others_block_cluster_field_corrdinators_male=others_block_cluster_field_corrdinators_male or None, others_block_cluster_field_corrdinators_female=others_block_cluster_field_corrdinators_female or None, others_block_cluster_field_corrdinators_total=others_block_cluster_field_corrdinators_total or None,
            others_ngo_staff_corrdinators_male=others_ngo_staff_corrdinators_male or None, others_ngo_staff_corrdinators_female=others_ngo_staff_corrdinators_female or None, others_ngo_staff_corrdinators_total=others_ngo_staff_corrdinators_total or None,
            others_male=others_male or None, others_female=others_female or None, others_total=others_total or None,
            total_male=total_male or None, total_female=total_female or None, total=total, task=task, site_id = current_site,
            )
            stakeholders_obj.save()
            return redirect('/po-report/rnp/stakeholders-listing/'+str(task_id))
        else:
            error_message = 'Please, Enter the any one Category of participants for Achieved in this month'
    return render(request, 'po_report/rnp/stakeholders/add_stakeholders.html', locals())


@ login_required(login_url='/login/')
def edit_stakeholders_rnp_po_report(request, stakeholders_id, task_id):
    heading = "Section 10: Edit of capacity building of different stakeholders"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    stakeholders_obj = Stakeholder.objects.get(id=stakeholders_id)
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    if request.method == 'POST':
        data = request.POST
        master_trainers_male = data.get('master_trainers_male')
        master_trainers_female = data.get('master_trainers_female')
        master_trainers_total = data.get('master_trainers_total')
        nodal_teachers_male = data.get('nodal_teachers_male')
        nodal_teachers_female = data.get('nodal_teachers_female')
        nodal_teachers_total = data.get('nodal_teachers_total')
        principals_male = data.get('principals_male')
        principals_female = data.get('principals_female')
        principals_total = data.get('principals_total')
        district_level_officials_male = data.get('district_level_officials_male')
        district_level_officials_female = data.get('district_level_officials_female')
        district_level_officials_total = data.get('district_level_officials_total')
        peer_educator_male = data.get('peer_educator_male')
        peer_educator_female = data.get('peer_educator_female')
        peer_educator_total = data.get('peer_educator_total')
        state_level_officials_male = data.get('state_level_officials_male')
        state_level_officials_female = data.get('state_level_officials_female')
        state_level_officials_total = data.get('state_level_officials_total')
        icds_awws_male = data.get('icds_awws_male')
        icds_awws_female = data.get('icds_awws_female')
        icds_awws_total = data.get('icds_awws_total')
        icds_supervisors_male = data.get('icds_supervisors_male')
        icds_supervisors_female = data.get('icds_supervisors_female')
        icds_supervisors_total = data.get('icds_supervisors_total')
        icds_peer_educator_male = data.get('icds_peer_educator_male')
        icds_peer_educator_female = data.get('icds_peer_educator_female')
        icds_peer_educator_total = data.get('icds_peer_educator_total')
        icds_child_developement_project_officers_male = data.get('icds_child_developement_project_officers_male')
        icds_child_developement_project_officers_female = data.get('icds_child_developement_project_officers_female')
        icds_child_developement_project_officers_total = data.get('icds_child_developement_project_officers_total')
        icds_district_level_officials_male = data.get('icds_district_level_officials_male')
        icds_district_level_officials_female = data.get('icds_district_level_officials_female')
        icds_district_level_officials_total = data.get('icds_district_level_officials_total')
        icds_state_level_officials_male = data.get('icds_state_level_officials_male')
        icds_state_level_officials_female = data.get('icds_state_level_officials_female')
        icds_state_level_officials_total = data.get('icds_state_level_officials_total')
        health_ashas_male = data.get('health_ashas_male')
        health_ashas_female = data.get('health_ashas_female')
        health_ashas_total = data.get('health_ashas_total')
        health_anms_male = data.get('health_anms_male')
        health_anms_female = data.get('health_anms_female')
        health_anms_total = data.get('health_anms_total')
        health_bpm_bhm_pheos_male = data.get('health_bpm_bhm_pheos_male')
        health_bpm_bhm_pheos_female = data.get('health_bpm_bhm_pheos_female')
        health_bpm_bhm_pheos_total = data.get('health_bpm_bhm_pheos_total')
        health_medical_officers_male = data.get('health_medical_officers_male')
        health_medical_officers_female = data.get('health_medical_officers_female')
        health_medical_officers_total = data.get('health_medical_officers_total')
        health_district_level_officials_male = data.get('health_district_level_officials_male')
        health_district_level_officials_female = data.get('health_district_level_officials_female')
        health_district_level_officials_total = data.get('health_district_level_officials_total')
        health_state_level_officials_male = data.get('health_state_level_officials_male')
        health_state_level_officials_female = data.get('health_state_level_officials_female')
        health_state_level_officials_total = data.get('health_state_level_officials_total')
        health_rsk_male = data.get('health_rsk_male')
        health_rsk_female = data.get('health_rsk_female')
        health_rsk_total = data.get('health_rsk_total')
        health_peer_educator_male = data.get('health_peer_educator_male')
        health_peer_educator_female = data.get('health_peer_educator_female')
        health_peer_educator_total = data.get('health_peer_educator_total')
        panchayat_ward_members_male = data.get('panchayat_ward_members_male')
        panchayat_ward_members_female = data.get('panchayat_ward_members_female')
        panchayat_ward_members_total = data.get('panchayat_ward_members_total')
        panchayat_up_mukhiya_up_Pramukh_male = data.get('panchayat_up_mukhiya_up_Pramukh_male')
        panchayat_up_mukhiya_up_Pramukh_female = data.get('panchayat_up_mukhiya_up_Pramukh_female')
        panchayat_up_mukhiya_up_Pramukh_total = data.get('panchayat_up_mukhiya_up_Pramukh_total')
        panchayat_mukhiya_Pramukh_male = data.get('panchayat_mukhiya_Pramukh_male')
        panchayat_mukhiya_Pramukh_female = data.get('panchayat_mukhiya_Pramukh_female')
        panchayat_mukhiya_Pramukh_total = data.get('panchayat_mukhiya_Pramukh_total')
        panchayat_samiti_member_male = data.get('panchayat_samiti_member_male')
        panchayat_samiti_member_female = data.get('panchayat_samiti_member_female')
        panchayat_samiti_member_total = data.get('panchayat_samiti_member_total')
        panchayat_zila_parishad_member_male = data.get('panchayat_zila_parishad_member_male')
        panchayat_zila_parishad_member_female = data.get('panchayat_zila_parishad_member_female')
        panchayat_zila_parishad_member_total = data.get('panchayat_zila_parishad_member_total')
        panchayat_vc_zila_parishad_male = data.get('panchayat_vc_zila_parishad_male')
        panchayat_vc_zila_parishad_female = data.get('panchayat_vc_zila_parishad_female')
        panchayat_vc_zila_parishad_total = data.get('panchayat_vc_zila_parishad_total')
        panchayat_chairman_zila_parishad_male = data.get('panchayat_chairman_zila_parishad_male')
        panchayat_chairman_zila_parishad_female = data.get('panchayat_chairman_zila_parishad_female')
        panchayat_chairman_zila_parishad_total = data.get('panchayat_chairman_zila_parishad_total')
        panchayat_block_level_officials_male = data.get('panchayat_block_level_officials_male')
        panchayat_block_level_officials_female = data.get('panchayat_block_level_officials_female')
        panchayat_block_level_officials_total = data.get('panchayat_block_level_officials_total')
        panchayat_district_level_officials_male = data.get('panchayat_district_level_officials_male')
        panchayat_district_level_officials_female = data.get('panchayat_district_level_officials_female')
        panchayat_district_level_officials_total = data.get('panchayat_district_level_officials_total')
        panchayat_state_level_officials_male = data.get('panchayat_state_level_officials_male')
        panchayat_state_level_officials_female = data.get('panchayat_state_level_officials_female')
        panchayat_state_level_officials_total = data.get('panchayat_state_level_officials_total')
        media_interns_male = data.get('media_interns_male')
        media_interns_female = data.get('media_interns_female')
        media_interns_total = data.get('media_interns_total')
        media_journalists_male = data.get('media_journalists_male')
        media_journalists_female = data.get('media_journalists_female')
        media_journalists_total = data.get('media_journalists_total')
        media_editors_male = data.get('media_editors_male')
        media_editors_female = data.get('media_editors_female')
        media_editors_total = data.get('media_editors_total')
        others_block_cluster_field_corrdinators_male = data.get('others_block_cluster_field_corrdinators_male')
        others_block_cluster_field_corrdinators_female = data.get('others_block_cluster_field_corrdinators_female')
        others_block_cluster_field_corrdinators_total = data.get('others_block_cluster_field_corrdinators_total')
        others_ngo_staff_corrdinators_male = data.get('others_ngo_staff_corrdinators_male')
        others_ngo_staff_corrdinators_female = data.get('others_ngo_staff_corrdinators_female')
        others_ngo_staff_corrdinators_total = data.get('others_ngo_staff_corrdinators_total')
        others_male = data.get('others_male')
        others_female = data.get('others_female')
        others_total = data.get('others_total')
        total_male = data.get('total_male')
        total_female = data.get('total_female')
        total = data.get('total')
        task = Task.objects.get(id=task_id)
        if total and int(total) != 0:
            stakeholders_obj.user_name_id = request.user
            stakeholders_obj.master_trainers_male = master_trainers_male or None
            stakeholders_obj.master_trainers_female = master_trainers_female or None
            stakeholders_obj.master_trainers_total = master_trainers_total or None
            stakeholders_obj.nodal_teachers_male = nodal_teachers_male or None
            stakeholders_obj.nodal_teachers_female = nodal_teachers_female or None
            stakeholders_obj.nodal_teachers_total = nodal_teachers_total or None
            stakeholders_obj.principals_male = principals_male or None
            stakeholders_obj.principals_female = principals_female or None
            stakeholders_obj.principals_total = principals_total or None
            stakeholders_obj.district_level_officials_male = district_level_officials_male or None
            stakeholders_obj.district_level_officials_female = district_level_officials_female or None
            stakeholders_obj.district_level_officials_total = district_level_officials_total or None
            stakeholders_obj.peer_educator_male = peer_educator_male or None
            stakeholders_obj.peer_educator_female = peer_educator_female or None
            stakeholders_obj.peer_educator_total = peer_educator_total or None
            stakeholders_obj.state_level_officials_male = state_level_officials_male or None
            stakeholders_obj.state_level_officials_female = state_level_officials_female or None
            stakeholders_obj.state_level_officials_total = state_level_officials_total or None
            stakeholders_obj.icds_awws_male = icds_awws_male or None
            stakeholders_obj.icds_awws_female = icds_awws_female or None
            stakeholders_obj.icds_awws_total = icds_awws_total or None
            stakeholders_obj.icds_supervisors_male = icds_supervisors_male or None
            stakeholders_obj.icds_supervisors_female = icds_supervisors_female or None
            stakeholders_obj.icds_supervisors_total = icds_supervisors_total or None
            stakeholders_obj.icds_peer_educator_male = icds_peer_educator_male or None
            stakeholders_obj.icds_peer_educator_female = icds_peer_educator_female or None
            stakeholders_obj.icds_peer_educator_total = icds_peer_educator_total or None
            stakeholders_obj.icds_child_developement_project_officers_male = icds_child_developement_project_officers_male or None
            stakeholders_obj.icds_child_developement_project_officers_female = icds_child_developement_project_officers_female or None
            stakeholders_obj.icds_child_developement_project_officers_total = icds_child_developement_project_officers_total or None
            stakeholders_obj.icds_district_level_officials_male = icds_district_level_officials_male or None
            stakeholders_obj.icds_district_level_officials_female = icds_district_level_officials_female or None
            stakeholders_obj.icds_district_level_officials_total = icds_district_level_officials_total or None
            stakeholders_obj.icds_state_level_officials_male = icds_state_level_officials_male or None
            stakeholders_obj.icds_state_level_officials_female = icds_state_level_officials_female or None
            stakeholders_obj.icds_state_level_officials_total = icds_state_level_officials_total or None
            stakeholders_obj.health_ashas_male = health_ashas_male or None
            stakeholders_obj.health_ashas_female = health_ashas_female or None
            stakeholders_obj.health_ashas_total = health_ashas_total or None
            stakeholders_obj.health_anms_male = health_anms_male or None
            stakeholders_obj.health_anms_female = health_anms_female or None
            stakeholders_obj.health_anms_total = health_anms_total or None
            stakeholders_obj.health_bpm_bhm_pheos_male = health_bpm_bhm_pheos_male or None
            stakeholders_obj.health_bpm_bhm_pheos_female = health_bpm_bhm_pheos_female or None
            stakeholders_obj.health_bpm_bhm_pheos_total = health_bpm_bhm_pheos_total or None
            stakeholders_obj.health_medical_officers_male = health_medical_officers_male or None
            stakeholders_obj.health_medical_officers_female = health_medical_officers_female or None
            stakeholders_obj.health_medical_officers_total = health_medical_officers_total or None
            stakeholders_obj.health_district_level_officials_male = health_district_level_officials_male or None
            stakeholders_obj.health_district_level_officials_female = health_district_level_officials_female or None
            stakeholders_obj.health_district_level_officials_total = health_district_level_officials_total or None
            stakeholders_obj.health_state_level_officials_male = health_state_level_officials_male or None
            stakeholders_obj.health_state_level_officials_female = health_state_level_officials_female or None
            stakeholders_obj.health_state_level_officials_total = health_state_level_officials_total or None
            stakeholders_obj.health_rsk_male = health_rsk_male or None
            stakeholders_obj.health_rsk_female = health_rsk_female or None
            stakeholders_obj.health_rsk_total = health_rsk_total or None
            stakeholders_obj.health_peer_educator_male = health_peer_educator_male or None
            stakeholders_obj.health_peer_educator_female = health_peer_educator_female or None
            stakeholders_obj.health_peer_educator_total = health_peer_educator_total or None
            stakeholders_obj.panchayat_ward_members_male = panchayat_ward_members_male or None
            stakeholders_obj.panchayat_ward_members_female = panchayat_ward_members_female or None
            stakeholders_obj.panchayat_ward_members_total = panchayat_ward_members_total or None
            stakeholders_obj.panchayat_up_mukhiya_up_Pramukh_male = panchayat_up_mukhiya_up_Pramukh_male or None
            stakeholders_obj.panchayat_up_mukhiya_up_Pramukh_female = panchayat_up_mukhiya_up_Pramukh_female or None
            stakeholders_obj.panchayat_up_mukhiya_up_Pramukh_total = panchayat_up_mukhiya_up_Pramukh_total or None
            stakeholders_obj.panchayat_mukhiya_Pramukh_male = panchayat_mukhiya_Pramukh_male or None
            stakeholders_obj.panchayat_mukhiya_Pramukh_female = panchayat_mukhiya_Pramukh_female or None
            stakeholders_obj.panchayat_mukhiya_Pramukh_total = panchayat_mukhiya_Pramukh_total or None
            stakeholders_obj.panchayat_samiti_member_male = panchayat_samiti_member_male or None
            stakeholders_obj.panchayat_samiti_member_female = panchayat_samiti_member_female or None
            stakeholders_obj.panchayat_samiti_member_male = panchayat_samiti_member_total or None
            stakeholders_obj.panchayat_zila_parishad_member_male = panchayat_zila_parishad_member_male or None
            stakeholders_obj.panchayat_zila_parishad_member_female = panchayat_zila_parishad_member_female or None
            stakeholders_obj.panchayat_zila_parishad_member_total = panchayat_zila_parishad_member_total or None
            stakeholders_obj.panchayat_vc_zila_parishad_male = panchayat_vc_zila_parishad_male or None
            stakeholders_obj.panchayat_vc_zila_parishad_female = panchayat_vc_zila_parishad_female or None
            stakeholders_obj.panchayat_vc_zila_parishad_total = panchayat_vc_zila_parishad_total or None
            stakeholders_obj.panchayat_chairman_zila_parishad_male = panchayat_chairman_zila_parishad_male or None
            stakeholders_obj.panchayat_chairman_zila_parishad_female = panchayat_chairman_zila_parishad_female or None
            stakeholders_obj.panchayat_chairman_zila_parishad_total = panchayat_chairman_zila_parishad_total or None
            stakeholders_obj.panchayat_block_level_officials_male = panchayat_block_level_officials_male or None
            stakeholders_obj.panchayat_block_level_officials_female = panchayat_block_level_officials_female or None
            stakeholders_obj.panchayat_block_level_officials_total = panchayat_block_level_officials_total or None
            stakeholders_obj.panchayat_district_level_officials_male = panchayat_district_level_officials_male or None
            stakeholders_obj.panchayat_district_level_officials_female = panchayat_district_level_officials_female or None
            stakeholders_obj.panchayat_district_level_officials_total = panchayat_district_level_officials_total or None
            stakeholders_obj.panchayat_state_level_officials_male = panchayat_state_level_officials_male or None
            stakeholders_obj.panchayat_state_level_officials_female = panchayat_state_level_officials_female or None
            stakeholders_obj.panchayat_state_level_officials_total = panchayat_state_level_officials_total or None
            stakeholders_obj.media_interns_male = media_interns_male or None
            stakeholders_obj.media_interns_female = media_interns_female or None
            stakeholders_obj.media_interns_total = media_interns_total or None
            stakeholders_obj.media_journalists_male = media_journalists_male or None
            stakeholders_obj.media_journalists_female = media_journalists_female or None
            stakeholders_obj.media_journalists_total = media_journalists_total or None
            stakeholders_obj.media_editors_male = media_editors_male or None
            stakeholders_obj.media_editors_female = media_editors_female or None
            stakeholders_obj.media_editors_total = media_editors_total or None
            stakeholders_obj.others_block_cluster_field_corrdinators_male = others_block_cluster_field_corrdinators_male or None
            stakeholders_obj.others_block_cluster_field_corrdinators_female = others_block_cluster_field_corrdinators_female or None
            stakeholders_obj.others_block_cluster_field_corrdinators_total = others_block_cluster_field_corrdinators_total or None
            stakeholders_obj.others_ngo_staff_corrdinators_male = others_ngo_staff_corrdinators_male or None
            stakeholders_obj.others_ngo_staff_corrdinators_female = others_ngo_staff_corrdinators_female or None
            stakeholders_obj.others_ngo_staff_corrdinators_total = others_ngo_staff_corrdinators_total or None
            stakeholders_obj.others_male = others_male or None
            stakeholders_obj.others_female = others_female or None
            stakeholders_obj.others_total = others_total or None
            stakeholders_obj.total_male = total_male or None
            stakeholders_obj.total_female = total_female or None
            stakeholders_obj.total = total 
            stakeholders_obj.task_id = task
            stakeholders_obj.site_id =  current_site
            stakeholders_obj.save()
            return redirect('/po-report/rnp/stakeholders-listing/'+str(task_id))
        else:
            error_message = 'Please, Enter the any one Category of participants for Achieved in this month'
    return render(request, 'po_report/rnp/stakeholders/edit_stakeholders.html', locals())




@ login_required(login_url='/login/')
def sessions_monitoring_listing_rnp_po_report(request, task_id):
    heading = "Section 11: Details of sessions monitoring and handholding support at block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    village_id =CC_AWC_AH.objects.filter(status=1).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(status=1).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1).values_list('school__id')
    sessions_monitoring = SessionMonitoring.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, sessions_monitoring)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/sessions_monitoring/sessions_monitoring_listing.html', locals())


@ login_required(login_url='/login/')
def add_sessions_monitoring_rnp_po_report(request, task_id):
    heading = "Section 11: Add of sessions monitoring and handholding support at block level"
    current_site = request.session.get('site_id')
    user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    user_report_spo = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    village_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__id')
    school_id = CC_School.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('school__id')
    sessions_monitoring = SessionMonitoring.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    village_obj = Village.objects.filter(status=1, id__in=village_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')

    if request.method == 'POST':
        data = request.POST
        name_of_visited = data.get('name_of_visited')
        selected_field_other = data.get('selected_field_other')
        
        if name_of_visited == '1':
            content_type_model='village'
            selected_object_id=data.get('selected_field_village')
        elif name_of_visited == '2':
            content_type_model='awc'
            selected_object_id=data.get('selected_field_awc')
        else:
            content_type_model='school'
            selected_object_id=data.get('selected_field_school')

        date = data.get('date')
        sessions = data.getlist('session_attended')
        session_attended = ", ".join(sessions)
        observation = data.get('observation')
        recommendation = data.get('recommendation')
        task = Task.objects.get(id=task_id)

        sessions_monitoring = SessionMonitoring.objects.create(name_of_visited=name_of_visited, session_attended=session_attended,
        date=date,
        observation=observation, recommendation=recommendation, task=task, site_id = current_site)
        
        if selected_object_id:
            content_type = ContentType.objects.get(model=content_type_model)
            sessions_monitoring.content_type=content_type
            sessions_monitoring.object_id=selected_object_id
        
        if name_of_visited in ['4','5']:
            sessions_monitoring.name_of_place_visited = selected_field_other

        sessions_monitoring.save()
        return redirect('/po-report/rnp/sessions-monitoring-listing/'+str(task_id))
    return render(request, 'po_report/rnp/sessions_monitoring/add_sessions_monitoring.html', locals())


@ login_required(login_url='/login/')
def edit_sessions_monitoring_rnp_po_report(request, sessions_id, task_id):
    heading = "Section 11: Edit of sessions monitoring and handholding support at block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    user_report_spo = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    village_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__id')
    school_id = CC_School.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('school__id')
    sessions_monitoring = SessionMonitoring.objects.get(id=sessions_id)
    session_choice = sessions_monitoring.session_attended.split(', ')
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    village_obj = Village.objects.filter(status=1, id__in=village_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        selected_field_other = data.get('selected_field_other')
        name_of_visited = data.get('name_of_visited')
        if name_of_visited == '1':
            content_type_model='village'
            selected_object_id=data.get('selected_field_village')
        elif name_of_visited == '2':
            content_type_model='awc'
            selected_object_id=data.get('selected_field_awc')
        else:
            content_type_model='school'
            selected_object_id=data.get('selected_field_school')

        content_type = ContentType.objects.get(model=content_type_model)
        date = data.get('date')
        sessions = data.getlist('session_attended')
        session_attended = ", ".join(sessions)
        observation = data.get('observation')
        recommendation = data.get('recommendation')
        task = Task.objects.get(id=task_id)

        sessions_monitoring.name_of_visited = name_of_visited

        if selected_object_id:
            content_type = ContentType.objects.get(model=content_type_model)
            sessions_monitoring.content_type=content_type
            sessions_monitoring.object_id=selected_object_id

        if name_of_visited in ['4','5']:
            sessions_monitoring.name_of_place_visited = selected_field_other

        sessions_monitoring.date = date
        sessions_monitoring.session_attended = session_attended
        sessions_monitoring.observation = observation
        sessions_monitoring.recommendation = recommendation
        sessions_monitoring.task_id = task
        sessions_monitoring.site_id =  current_site
        sessions_monitoring.save()
        return redirect('/po-report/rnp/sessions-monitoring-listing/'+str(task_id))
    return render(request, 'po_report/rnp/sessions_monitoring/edit_sessions_monitoring.html', locals())



@ login_required(login_url='/login/')
def facility_visits_listing_rnp_po_report(request, task_id):
    heading = "Section 12: Details of events & facility visits at block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    user_report = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    village_id =CC_AWC_AH.objects.filter(status=1, user=user_report).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=user_report).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=user_report).values_list('school__id')
    facility_visits = Events.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, facility_visits)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/facility_visits/facility_visits_listing.html', locals())


@ login_required(login_url='/login/')
def add_facility_visits_rnp_po_report(request, task_id):
    heading = "Section 12: Add of events & facility visits at block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    user_report_spo = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    village_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__id')
    school_id = CC_School.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('school__id')
    facility_visits = Events.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    village_obj = Village.objects.filter(status=1, id__in=village_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        name_of_visited = data.get('name_of_visited')
        selected_field_other = data.get('selected_field_other')
        if name_of_visited == '1':
            content_type_model='village'
            selected_object_id=data.get('selected_field_village')
        elif name_of_visited == '2':
            content_type_model='awc'
            selected_object_id=data.get('selected_field_awc')
        else:
            content_type_model='school'
            selected_object_id=data.get('selected_field_school')

        date = data.get('date')
        purpose_visited = data.get('purpose_visited')
        observation = data.get('observation')
        recommendation = data.get('recommendation')
        task = Task.objects.get(id=task_id)

        
        facility_visits = Events.objects.create(name_of_visited=name_of_visited, purpose_visited=purpose_visited,
        date=date,
        observation=observation, recommendation=recommendation, task=task, site_id = current_site)
        
        if selected_object_id:
            content_type = ContentType.objects.get(model=content_type_model)
            facility_visits.content_type=content_type
            facility_visits.object_id=selected_object_id

        if name_of_visited in ['4','5','6','7','8','9','10','11']:
            facility_visits.name_of_place_visited = selected_field_other

        facility_visits.save()
        return redirect('/po-report/rnp/facility-visits-listing/'+str(task_id))
    return render(request, 'po_report/rnp/facility_visits/add_facility_visits.html', locals())


@ login_required(login_url='/login/')
def edit_facility_visits_rnp_po_report(request, facility_id, task_id):
    heading = "Section 12: Edit of events & facility visits at block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    user_report_spo = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    village_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__id')
    school_id = CC_School.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('school__id')
    facility_visits = Events.objects.get(id=facility_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    village_obj = Village.objects.filter(status=1, id__in=village_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        name_of_visited = data.get('name_of_visited')
        selected_field_other = data.get('selected_field_other')
        if name_of_visited == '1':
            content_type_model='village'
            selected_object_id=data.get('selected_field_village')
        elif name_of_visited == '2':
            content_type_model='awc'
            selected_object_id=data.get('selected_field_awc')
        else:
            content_type_model='school'
            selected_object_id=data.get('selected_field_school')

        date = data.get('date')
        purpose_visited = data.get('purpose_visited')
        observation = data.get('observation')
        recommendation = data.get('recommendation')
        task = Task.objects.get(id=task_id)

        facility_visits.name_of_visited = name_of_visited

        if selected_object_id:
            content_type = ContentType.objects.get(model=content_type_model)
            facility_visits.content_type = content_type
            facility_visits.object_id = selected_object_id
        
        if name_of_visited in ['4','5','6','7','8','9','10','11']:
            facility_visits.name_of_place_visited = selected_field_other

        facility_visits.date = date
        facility_visits.purpose_visited = purpose_visited
        facility_visits.observation = observation
        facility_visits.recommendation = recommendation
        facility_visits.task_id = task
        facility_visits.site_id =  current_site
        facility_visits.save()
        return redirect('/po-report/rnp/facility-visits-listing/'+str(task_id))
    return render(request, 'po_report/rnp/facility_visits/edit_facility_visits.html', locals())



@ login_required(login_url='/login/')
def followup_liaision_listing_rnp_po_report(request, task_id):
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    heading = "Section 14: Details of one to one (Follow up/ Liaison) meetings at district & Block Level"
    followup_liaision = FollowUP_LiaisionMeeting.objects.filter(user_name=request.user.id, task__id = task_id)
    data = pagination_function(request, followup_liaision)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/followup_liaision/followup_liaision_listing.html', locals())


@ login_required(login_url='/login/')
def add_followup_liaision_rnp_po_report(request, task_id):
    heading = "Section 14: Add of one to one (Follow up/ Liaison) meetings at district & Block Level"
    current_site = request.session.get('site_id')
    followup_liaision = FollowUP_LiaisionMeeting.objects.filter()
    meeting_obj = MasterLookUp.objects.filter(parent__slug = 'meeting-with-designation')
    if request.method == 'POST':
        data = request.POST
        date = data.get('date')
        district_block_level = data.get('district_block_level')
        meeting_id = data.get('meeting')
        meeting = MasterLookUp.objects.get(id = meeting_id)
        departments = data.get('departments')
        point_of_discussion = data.get('point_of_discussion')
        outcome = data.get('outcome')
        decision_taken = data.get('decision_taken')
        remarks = data.get('remarks')
        task = Task.objects.get(id=task_id)

        followup_liaision = FollowUP_LiaisionMeeting.objects.create(user_name=request.user, date=date,
        district_block_level=district_block_level, meeting_name=meeting, departments=departments, point_of_discussion=point_of_discussion,
        outcome=outcome, decision_taken=decision_taken, remarks=remarks, site_id = current_site, task=task)
        followup_liaision.save()
        return redirect('/po-report/rnp/followup-liaision-listing/'+str(task_id))
    return render(request, 'po_report/rnp/followup_liaision/add_followup_liaision.html', locals())


@ login_required(login_url='/login/')
def edit_followup_liaision_rnp_po_report(request, followup_liaision_id, task_id):
    heading = "Section 14: Edit of one to one (Follow up/ Liaison) meetings at district & Block Level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    followup_liaision = FollowUP_LiaisionMeeting.objects.get(id=followup_liaision_id)
    meeting_obj = MasterLookUp.objects.filter(parent__slug = 'meeting-with-designation')
    if request.method == 'POST':
        data = request.POST
        date = data.get('date')
        district_block_level = data.get('district_block_level')
        meeting_id = data.get('meeting')
        meeting = MasterLookUp.objects.get(id = meeting_id)
        departments = data.get('departments')
        point_of_discussion = data.get('point_of_discussion')
        outcome = data.get('outcome')
        decision_taken = data.get('decision_taken')
        remarks = data.get('remarks')
        task = Task.objects.get(id=task_id)


        followup_liaision.user_name = request.user
        followup_liaision.date = date
        followup_liaision.district_block_level = district_block_level
        followup_liaision.meeting_name = meeting
        followup_liaision.departments = departments
        followup_liaision.point_of_discussion = point_of_discussion
        followup_liaision.outcome = outcome
        followup_liaision.decision_taken = decision_taken
        followup_liaision.remarks = remarks
        followup_liaision.task_id = task
        followup_liaision.site_id =  current_site
        followup_liaision.save()
        return redirect('/po-report/rnp/followup-liaision-listing/'+str(task_id))
    return render(request, 'po_report/rnp/followup_liaision/edit_followup_liaision.html', locals())



@ login_required(login_url='/login/')
def participating_meeting_listing_rnp_po_report(request, task_id):
    heading = "Section 13: Details of participating in meetings at district and block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    participating_meeting = ParticipatingMeeting.objects.filter(user_name=request.user.id, task__id = task_id)
    data = pagination_function(request, participating_meeting)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/participating_meeting/participating_meeting_listing.html', locals())

@ login_required(login_url='/login/')
def add_participating_meeting_rnp_po_report(request, task_id):
    heading = "Section 13: Add of participating in meetings at district and block level"
    current_site = request.session.get('site_id')
    participating_meeting = ParticipatingMeeting.objects.filter()
    if request.method == 'POST':
        data = request.POST
        type_of_meeting = data.get('type_of_meeting')
        district_block_level = data.get('district_block_level')
        department = data.get('department')
        point_of_discussion = data.get('point_of_discussion')
        districit_level_officials = data.get('districit_level_officials')
        block_level = data.get('block_level')
        cluster_level = data.get('cluster_level')
        no_of_pri = data.get('no_of_pri')
        no_of_others = data.get('no_of_others')
        date = data.get('date')
        task = Task.objects.get(id=task_id)
        participating_meeting = ParticipatingMeeting.objects.create(user_name=request.user, type_of_meeting=type_of_meeting,
        department=department, point_of_discussion=point_of_discussion, districit_level_officials=districit_level_officials,
        block_level=block_level, cluster_level=cluster_level, no_of_pri=no_of_pri, no_of_others=no_of_others,
        district_block_level=district_block_level, date=date, task=task, site_id = current_site,)
        participating_meeting.save()
        return redirect('/po-report/rnp/participating-meeting-listing/'+str(task_id))
    return render(request, 'po_report/rnp/participating_meeting/add_participating_meeting.html', locals())

@ login_required(login_url='/login/')
def edit_participating_meeting_rnp_po_report(request, participating_id, task_id):
    heading = "Section 13: Edit of participating in meetings at district and block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    participating_meeting = ParticipatingMeeting.objects.get(id=participating_id)
    if request.method == 'POST':
        data = request.POST
        type_of_meeting = data.get('type_of_meeting')
        department = data.get('department')
        district_block_level = data.get('district_block_level')
        point_of_discussion = data.get('point_of_discussion')
        districit_level_officials = data.get('districit_level_officials')
        block_level = data.get('block_level')
        cluster_level = data.get('cluster_level')
        no_of_pri = data.get('no_of_pri')
        no_of_others = data.get('no_of_others')
        date = data.get('date')
        task = Task.objects.get(id=task_id)

        participating_meeting.user_name = request.user
        participating_meeting.type_of_meeting = type_of_meeting
        participating_meeting.district_block_level = district_block_level
        participating_meeting.department = department
        participating_meeting.point_of_discussion = point_of_discussion
        participating_meeting.districit_level_officials = districit_level_officials
        participating_meeting.block_level = block_level
        participating_meeting.cluster_level = cluster_level
        participating_meeting.no_of_pri = no_of_pri
        participating_meeting.no_of_others = no_of_others
        participating_meeting.date = date
        participating_meeting.task_id = task
        participating_meeting.site_id =  current_site
        participating_meeting.save()
        return redirect('/po-report/rnp/participating-meeting-listing/'+str(task_id))
    return render(request, 'po_report/rnp/participating_meeting/edit_participating_meeting.html', locals())


@ login_required(login_url='/login/')
def faced_related_listing_rnp_po_report(request, task_id):
    heading = "Section 15: Details of faced related"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    faced_related = FacedRelatedOperation.objects.filter(user_name=request.user.id, task__id = task_id)
    data = pagination_function(request, faced_related)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/rnp/faced_related/faced_related_listing.html', locals())

@ login_required(login_url='/login/')
def add_faced_related_rnp_po_report(request, task_id):
    heading = "Section 15: Add of faced related"
    current_site = request.session.get('site_id')
    faced_related = FacedRelatedOperation.objects.filter()
    if request.method == 'POST':
        data = request.POST
        challenges = data.get('challenges')
        proposed_solution = data.get('proposed_solution')
        task = Task.objects.get(id=task_id)

        # if FacedRelatedOperation.objects.filter(Q(challenges__isnull=challenges) & Q(proposed_solution__isnull=proposed_solution)).exists():
        if challenges or proposed_solution:
            faced_related = FacedRelatedOperation.objects.create(user_name=request.user, challenges=challenges,
            proposed_solution=proposed_solution, task=task, site_id = current_site)
            faced_related.save()
        else:
            return redirect('/po-report/rnp/faced-related-listing/'+str(task_id))
        return redirect('/po-report/rnp/faced-related-listing/'+str(task_id))
    return render(request, 'po_report/rnp/faced_related/add_faced_related.html', locals())


@ login_required(login_url='/login/')
def edit_faced_related_rnp_po_report(request, faced_related_id, task_id):
    heading = "Section 15: Edit of faced related"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    faced_related = FacedRelatedOperation.objects.get(id=faced_related_id)
    if request.method == 'POST':
        data = request.POST
        challenges = data.get('challenges')
        proposed_solution = data.get('proposed_solution')
        task = Task.objects.get(id=task_id)

        # if FacedRelatedOperation.objects.filter(Q(challenges__isnull=challenges) & Q(proposed_solution__isnull=proposed_solution)).exists():
        if challenges or proposed_solution:
            faced_related.user_name = request.user
            faced_related.challenges = challenges
            faced_related.proposed_solution = proposed_solution
            faced_related.task_id = task
            faced_related.site_id =  current_site
            faced_related.save()
        else:
            return redirect('/po-report/fossil/faced-related-listing/'+str(task_id))
        return redirect('/po-report/rnp/faced-related-listing/'+str(task_id))
    return render(request, 'po_report/rnp/faced_related/edit_faced_related.html', locals())


#--- ---------po-report-un-trust--------------

@ login_required(login_url='/login/')
def health_sessions_listing_untrust_po_report(request, task_id):
    heading = "Section 1: Details of transaction of sessions on health & nutrition"
    # awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, health_sessions)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/health_sessions/health_sessions_listing.html', locals())

@ login_required(login_url='/login/')
def add_health_sessions_untrust_po_report(request, task_id):
    heading = "Section 1: Add of transaction of sessions on health & nutrition"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    fossil_ah_session_category_obj =  FossilAHSessionCategory.objects.filter(status=1)
  
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_selected_id = data.get('awc_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_ah_session_id = data.get('fossil_ah_session')
        fossil_ah_session_selected_id = data.get('fossil_ah_session_category')
        fossil_ah_session = FossilAHSession.objects.get(id=fossil_ah_session_id)
        date_of_session = data.get('date_of_session')
        adolescent_obj =  Adolescent.objects.filter(awc__id=adolescent_selected_id, site=current_site)
        fossil_ah_session_obj =  FossilAHSession.objects.filter(fossil_ah_session_category__id = fossil_ah_session_selected_id)
        session_day = data.get('session_day')
        age = data.get('age')
        gender = data.get('gender')
        facilitator_name = data.get('facilitator_name')
        designations = data.get('designations')
        task = Task.objects.get(id=task_id)
        if AHSession.objects.filter(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
                                    date_of_session=date_of_session,  status=1).exists():
            exist_error = "Please try again this data already exists!!!"
            return render(request,'po_report/untrust/health_sessions/add_health_sessions.html', locals())
        else:
            health_sessions = AHSession.objects.create(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
            date_of_session=date_of_session, session_day=session_day,designation_data = designations,
            age=age, gender=gender, facilitator_name = facilitator_name, task=task, site_id = current_site)
            health_sessions.save()
        return redirect('/po-report/untrust/health-sessions-listing/'+str(task_id))
    return render(request, 'po_report/untrust/health_sessions/add_health_sessions.html', locals())


@ login_required(login_url='/login/')
def edit_health_sessions_untrust_po_report(request, ahsession_id, task_id):
    heading = "Section 1: Edit of transaction of sessions on health & nutrition"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    health_sessions = AHSession.objects.get(id=ahsession_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id=health_sessions.adolescent_name.awc.id, site=current_site)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    fossil_ah_session_obj =  FossilAHSession.objects.filter(status=1, fossil_ah_session_category__id=health_sessions.fossil_ah_session.fossil_ah_session_category.id)
    fossil_ah_session_category_obj =  FossilAHSessionCategory.objects.filter(status=1,)
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        fossil_ah_session_id = data.get('fossil_ah_session')
        fossil_ah_session = FossilAHSession.objects.get(id=fossil_ah_session_id)
        date_of_session = data.get('date_of_session')
        session_day = data.get('session_day')
        age = data.get('age')
        gender = data.get('gender')
        facilitator_name = data.get('facilitator_name')
        designations = data.get('designations')
        task = Task.objects.get(id=task_id)
        if AHSession.objects.filter(adolescent_name=adolescent_name, fossil_ah_session=fossil_ah_session,
                                    date_of_session=date_of_session,  status=1).exclude(id=ahsession_id).exists():
            exist_error = "Please try again this data already exists!!!"
            return render(request,'po_report/untrust/health_sessions/edit_health_sessions.html', locals())
        else:
            health_sessions.adolescent_name_id = adolescent_name
            health_sessions.fossil_ah_session_id = fossil_ah_session
            health_sessions.date_of_session = date_of_session
            health_sessions.age = age
            health_sessions.gender = gender
            health_sessions.session_day = session_day
            health_sessions.designation_data = designations
            health_sessions.facilitator_name = facilitator_name
            health_sessions.task_id = task
            health_sessions.site_id =  current_site
            health_sessions.save()
        return redirect('/po-report/untrust/health-sessions-listing/'+str(task_id))
    return render(request, 'po_report/untrust/health_sessions/edit_health_sessions.html', locals())


@ login_required(login_url='/login/')
def girls_ahwd_listing_untrust_po_report(request, task_id):
    heading = "Section 3(a): Details of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, girls_ahwd)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/girls_ahwd/girls_ahwd_listing.html', locals())


@ login_required(login_url='/login/')
def add_girls_ahwd_untrust_po_report(request, task_id):
    heading = "Section 3(a): Add of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    school_obj = School.objects.filter(status=1, id__in=school_id)
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        tt_10_14_years = data.get('tt_10_14_years')
        tt_15_19_years = data.get('tt_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        girls_ahwd = GirlsAHWD.objects.create(place_of_ahwd=place_of_ahwd, content_type=content_type, object_id=selected_object_id,
        participated_10_14_years=participated_10_14_years, date_of_ahwd=date_of_ahwd, hwc_name=hwc_name,
        participated_15_19_years=participated_15_19_years, bmi_10_14_years=bmi_10_14_years,
        bmi_15_19_years=bmi_15_19_years, hb_10_14_years=hb_10_14_years, hb_15_19_years=hb_15_19_years,
        tt_10_14_years=tt_10_14_years, tt_15_19_years=tt_15_19_years, counselling_10_14_years=counselling_10_14_years,
        counselling_15_19_years=counselling_15_19_years, referral_10_14_years=referral_10_14_years,
        referral_15_19_years=referral_15_19_years, task=task, site_id = current_site)
        girls_ahwd.save()
        return redirect('/po-report/untrust/girls-ahwd-listing/'+str(task_id))
    return render(request, 'po_report/untrust/girls_ahwd/add_girls_ahwd.html', locals())


@ login_required(login_url='/login/')
def edit_girls_ahwd_untrust_po_report(request, girls_ahwd_id, task_id):
    heading = "Section 3(a): Edit of participation of adolescent girls in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    girls_ahwd = GirlsAHWD.objects.get(id=girls_ahwd_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    school_obj = School.objects.filter(status=1, id__in=school_id)
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        tt_10_14_years = data.get('tt_10_14_years')
        tt_15_19_years = data.get('tt_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        girls_ahwd.place_of_ahwd = place_of_ahwd
        girls_ahwd.content_type = content_type
        girls_ahwd.object_id = selected_object_id
        girls_ahwd.hwc_name = hwc_name
        girls_ahwd.date_of_ahwd = date_of_ahwd
        girls_ahwd.participated_10_14_years = participated_10_14_years
        girls_ahwd.participated_15_19_years = participated_15_19_years
        girls_ahwd.bmi_10_14_years = bmi_10_14_years
        girls_ahwd.bmi_15_19_years = bmi_15_19_years
        girls_ahwd.hb_10_14_years = hb_10_14_years
        girls_ahwd.hb_15_19_years = hb_15_19_years
        girls_ahwd.tt_10_14_years = tt_10_14_years
        girls_ahwd.tt_15_19_years = tt_15_19_years
        girls_ahwd.counselling_10_14_years = counselling_10_14_years
        girls_ahwd.counselling_15_19_years = counselling_15_19_years
        girls_ahwd.referral_10_14_years = referral_10_14_years
        girls_ahwd.referral_15_19_years = referral_15_19_years
        girls_ahwd.task_id = task
        girls_ahwd.site_id =  current_site
        girls_ahwd.save()
        return redirect('/po-report/untrust/girls-ahwd-listing/'+str(task_id))
    return render(request, 'po_report/untrust/girls_ahwd/edit_girls_ahwd.html', locals())




@ login_required(login_url='/login/')
def boys_ahwd_listing_untrust_po_report(request, task_id):
    heading = "Section 3(b): Details of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, boys_ahwd)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/boys_ahwd/boys_ahwd_listing.html', locals())


@ login_required(login_url='/login/')
def add_boys_ahwd_untrust_po_report(request, task_id):
    heading = "Section 3(b): Add of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    school_obj = School.objects.filter(status=1, id__in=school_id)
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        boys_ahwd = BoysAHWD.objects.create(place_of_ahwd=place_of_ahwd, content_type=content_type, object_id=selected_object_id,
        participated_10_14_years=participated_10_14_years, date_of_ahwd=date_of_ahwd, hwc_name=hwc_name,
        participated_15_19_years=participated_15_19_years, bmi_10_14_years=bmi_10_14_years,
        bmi_15_19_years=bmi_15_19_years, hb_10_14_years=hb_10_14_years, hb_15_19_years=hb_15_19_years,
        counselling_10_14_years=counselling_10_14_years,
        counselling_15_19_years=counselling_15_19_years, referral_10_14_years=referral_10_14_years,
        referral_15_19_years=referral_15_19_years, task=task, site_id = current_site)
        boys_ahwd.save()
        return redirect('/po-report/untrust/boys-ahwd-listing/'+str(task_id))
    return render(request, 'po_report/untrust/boys_ahwd/add_boys_ahwd.html', locals())


@ login_required(login_url='/login/')
def edit_boys_ahwd_untrust_po_report(request, boys_ahwd_id, task_id):
    heading = "Section 3(b): Edit of participation of adolescent boys in Adolescent Health Wellness Day (AHWD)"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    boys_ahwd = BoysAHWD.objects.get(id=boys_ahwd_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id)
    school_obj = School.objects.filter(status=1, id__in=school_id)
    if request.method == 'POST':
        data = request.POST
        place_of_ahwd = data.get('place_of_ahwd')
        if place_of_ahwd == '1':
            selected_object_id=data.get('selected_field_awc')
            content_type_model='awc'
            hwc_name = None
        elif place_of_ahwd == '2':
            selected_object_id=data.get('selected_field_school')
            content_type_model='school'
            hwc_name = None
        else:
            selected_object_id = None
            content_type_model = None
            hwc_name = data.get('hwc_name')
       
        content_type = ContentType.objects.get(model=content_type_model) if content_type_model != None else None
        date_of_ahwd = data.get('date_of_ahwd')
        participated_10_14_years = data.get('participated_10_14_years')
        participated_15_19_years = data.get('participated_15_19_years')
        bmi_10_14_years = data.get('bmi_10_14_years')
        bmi_15_19_years = data.get('bmi_15_19_years')
        hb_10_14_years = data.get('hb_10_14_years')
        hb_15_19_years = data.get('hb_15_19_years')
        counselling_10_14_years = data.get('counselling_10_14_years')
        counselling_15_19_years = data.get('counselling_15_19_years')
        referral_10_14_years = data.get('referral_10_14_years')
        referral_15_19_years = data.get('referral_15_19_years')
        task = Task.objects.get(id=task_id)

        boys_ahwd.place_of_ahwd = place_of_ahwd
        boys_ahwd.content_type = content_type
        boys_ahwd.object_id = selected_object_id
        boys_ahwd.hwc_name = hwc_name
        boys_ahwd.hwc_name = hwc_name
        boys_ahwd.date_of_ahwd = date_of_ahwd
        boys_ahwd.participated_10_14_years = participated_10_14_years
        boys_ahwd.participated_15_19_years = participated_15_19_years
        boys_ahwd.bmi_10_14_years = bmi_10_14_years
        boys_ahwd.bmi_15_19_years = bmi_15_19_years
        boys_ahwd.hb_10_14_years = hb_10_14_years
        boys_ahwd.hb_15_19_years = hb_15_19_years
        boys_ahwd.counselling_10_14_years = counselling_10_14_years
        boys_ahwd.counselling_15_19_years = counselling_15_19_years
        boys_ahwd.referral_10_14_years = referral_10_14_years
        boys_ahwd.referral_15_19_years = referral_15_19_years
        boys_ahwd.task_id = task
        boys_ahwd.site_id =  current_site
        boys_ahwd.save()
        return redirect('/po-report/untrust/boys-ahwd-listing/'+str(task_id))
    return render(request, 'po_report/untrust/boys_ahwd/edit_boys_ahwd.html', locals())




@ login_required(login_url='/login/')
def vocation_listing_untrust_po_report(request, task_id):
    heading = "Section 2(a): Details of adolescent linked with vocational training & placement"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj = AdolescentVocationalTraining.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, vocation_obj)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/voctional_training/vocation_listing.html', locals())

@ login_required(login_url='/login/')
def add_vocation_untrust_po_report(request, task_id):
    heading = "Section 2(a): Add of adolescent linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.filter()
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    tranining_sub_obj = TrainingSubject.objects.all()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id=training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)
        vocation_obj = AdolescentVocationalTraining.objects.create(adolescent_name=adolescent_name, date_of_registration=date_of_registration, 
        age=age, parent_guardian_name=parent_guardian_name, training_subject=training_subject,
        training_providing_by=training_providing_by, duration_days=duration_days, training_complated=training_complated, 
        placement_offered=placement_offered or None, placement_accepted=placement_accepted or None, type_of_employment=type_of_employment or None,
        task=task, site_id = current_site)
        vocation_obj.save()
        return redirect('/po-report/untrust/vocation-listing/'+str(task_id))
    return render(request, 'po_report/untrust/voctional_training/add_vocation_training.html', locals())


@ login_required(login_url='/login/')
def edit_vocation_untrust_po_report(request, vocation_id, task_id):
    heading = "Section 2(a): Edit of adolescent linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vocation_obj =  AdolescentVocationalTraining.objects.get(id=vocation_id)
    adolescent_obj =  Adolescent.objects.filter(awc__id__in=awc_id, site=current_site)
    tranining_sub_obj = TrainingSubject.objects.all()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id = training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)

        vocation_obj.adolescent_name_id = adolescent_name
        vocation_obj.date_of_registration = date_of_registration
        vocation_obj.age = age
        vocation_obj.parent_guardian_name = parent_guardian_name
        vocation_obj.training_subject = training_subject
        vocation_obj.training_providing_by = training_providing_by
        vocation_obj.duration_days = duration_days
        vocation_obj.training_complated = training_complated
        vocation_obj.placement_offered = placement_offered or None
        vocation_obj.placement_accepted = placement_accepted or None
        vocation_obj.type_of_employment = type_of_employment or None
        vocation_obj.task_id = task
        vocation_obj.site_id =  current_site
        vocation_obj.save()
        return redirect('/po-report/untrust/vocation-listing/'+str(task_id))
    return render(request, 'po_report/untrust/voctional_training/edit_vocation_training.html', locals())

@ login_required(login_url='/login/')
def parents_vocation_listing_untrust_po_report(request, task_id):
    heading = "Section 2(b): Details of parents linked with vocational training & placement"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    parents_vocation =  ParentVocationalTraining.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, parents_vocation)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/parents_voctional_training/vocation_listing.html', locals())

@ login_required(login_url='/login/')
def add_parents_vocation_untrust_po_report(request, task_id):
    heading = "Section 2(b): Edit of parents linked with vocational training & placement"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    parents_vocation =  ParentVocationalTraining.objects.filter()
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    tranining_sub_obj = TrainingSubject.objects.filter(status=1, )

    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_name = data.get('parent_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id = training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)
        parents_vocation = ParentVocationalTraining.objects.create(adolescent_name=adolescent_name, date_of_registration=date_of_registration, 
        age=age, parent_name=parent_name, training_subject=training_subject,
        training_providing_by=training_providing_by, duration_days=duration_days, training_complated=training_complated, 
        placement_offered=placement_offered  or None, placement_accepted=placement_accepted  or None, type_of_employment=type_of_employment  or None,
        task=task, site_id = current_site)
        parents_vocation.save()
        return redirect('/po-report/untrust/parents-vocation-listing/'+str(task_id))
    return render(request, 'po_report/untrust/parents_voctional_training/add_vocation_training.html', locals())


@ login_required(login_url='/login/')
def edit_parents_vocation_untrust_po_report(request, parent_id, task_id):
    current_site = request.session.get('site_id')
    heading = "Section 2(b): Edit of parents linked with vocational training & placement"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    parents_vocation =  ParentVocationalTraining.objects.get(id=parent_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    tranining_sub_obj = TrainingSubject.objects.filter(status=1)

    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        date_of_registration = data.get('date_of_registration')
        age = data.get('age')
        parent_name = data.get('parent_name')
        training_subject_id = data.get('training_subject')
        training_subject = TrainingSubject.objects.get(id = training_subject_id)
        training_providing_by = data.get('training_providing_by')
        duration_days = data.get('duration_days')
        training_complated = data.get('training_complated')
        placement_offered = data.get('placement_offered')
        placement_accepted = data.get('placement_accepted')
        type_of_employment = data.get('type_of_employment')
        task = Task.objects.get(id=task_id)

        parents_vocation.adolescent_name_id = adolescent_name
        parents_vocation.date_of_registration = date_of_registration
        parents_vocation.age = age
        parents_vocation.parent_name = parent_name
        parents_vocation.training_subject = training_subject
        parents_vocation.training_providing_by = training_providing_by
        parents_vocation.duration_days = duration_days
        parents_vocation.training_complated = training_complated
        parents_vocation.placement_offered = placement_offered  or None
        parents_vocation.placement_accepted = placement_accepted  or None
        parents_vocation.type_of_employment = type_of_employment  or None
        parents_vocation.task_id = task
        parents_vocation.site_id =  current_site
        parents_vocation.save()
        return redirect('/po-report/untrust/parents-vocation-listing/'+str(task_id))
    return render(request, 'po_report/untrust/parents_voctional_training/edit_vocation_training.html', locals())

@ login_required(login_url='/login/')
def adolescents_referred_listing_untrust_po_report(request, task_id):
    heading = "Section 4: Details of adolescents referred"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.filter(status=1, awc_name__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, adolescents_referred)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/adolescent_referred/adolescent_referred_listing.html', locals())

@ login_required(login_url='/login/')
def add_adolescents_referred_untrust_po_report(request, task_id):
    heading = "Section 4: Add of adolescents referred"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.filter()
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_referred_10_14_year = data.get('girls_referred_10_14_year')
        girls_referred_15_19_year = data.get('girls_referred_15_19_year')
        boys_referred_10_14_year = data.get('boys_referred_10_14_year')
        boys_referred_15_19_year = data.get('boys_referred_15_19_year')
        girls_hwc_referred = data.get('girls_hwc_referred')
        girls_hwc_visited = data.get('girls_hwc_visited')
        girls_afhc_referred = data.get('girls_afhc_referred')
        girls_afhc_visited = data.get('girls_afhc_visited')
        girls_dh_referred = data.get('girls_dh_referred')
        girls_dh_visited = data.get('girls_dh_visited')
        boys_hwc_referred = data.get('boys_hwc_referred')
        boys_hwc_visited = data.get('boys_hwc_visited')
        boys_afhc_referred = data.get('boys_afhc_referred')
        boys_afhc_visited = data.get('boys_afhc_visited')
        boys_dh_referred = data.get('boys_dh_referred')
        boys_dh_visited = data.get('boys_dh_visited')
        
        task = Task.objects.get(id=task_id)
        adolescents_referred = AdolescentsReferred.objects.create(awc_name=awc_name, girls_referred_10_14_year=girls_referred_10_14_year, 
        girls_referred_15_19_year=girls_referred_15_19_year, boys_referred_10_14_year=boys_referred_10_14_year, boys_referred_15_19_year=boys_referred_15_19_year,
        girls_hwc_referred=girls_hwc_referred, girls_hwc_visited=girls_hwc_visited, girls_afhc_referred=girls_afhc_referred, girls_afhc_visited=girls_afhc_visited,
        girls_dh_referred=girls_dh_referred, girls_dh_visited=girls_dh_visited, boys_hwc_referred=boys_hwc_referred, boys_hwc_visited=boys_hwc_visited,
        boys_afhc_referred=boys_afhc_referred, boys_afhc_visited=boys_afhc_visited, 
        boys_dh_referred=boys_dh_referred, boys_dh_visited=boys_dh_visited, task=task, site_id = current_site)
        adolescents_referred.save()
        return redirect('/po-report/untrust/adolescent-referred-listing/'+str(task_id))
    return render(request, 'po_report/untrust/adolescent_referred/add_adolescen_referred.html', locals())


@ login_required(login_url='/login/')
def edit_adolescents_referred_untrust_po_report(request, adolescents_referred_id, task_id):
    heading = "Section 4: Edit of adolescents referred"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescents_referred =  AdolescentsReferred.objects.get(id=adolescents_referred_id)
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_referred_10_14_year = data.get('girls_referred_10_14_year')
        girls_referred_15_19_year = data.get('girls_referred_15_19_year')
        boys_referred_10_14_year = data.get('boys_referred_10_14_year')
        boys_referred_15_19_year = data.get('boys_referred_15_19_year')
        girls_hwc_referred = data.get('girls_hwc_referred')
        girls_hwc_visited = data.get('girls_hwc_visited')
        girls_afhc_referred = data.get('girls_afhc_referred')
        girls_afhc_visited = data.get('girls_afhc_visited')
        girls_dh_referred = data.get('girls_dh_referred')
        girls_dh_visited = data.get('girls_dh_visited')
        boys_hwc_referred = data.get('boys_hwc_referred')
        boys_hwc_visited = data.get('boys_hwc_visited')
        boys_afhc_referred = data.get('boys_afhc_referred')
        boys_afhc_visited = data.get('boys_afhc_visited')
        boys_dh_referred = data.get('boys_dh_referred')
        boys_dh_visited = data.get('boys_dh_visited')  
        task = Task.objects.get(id=task_id)

        adolescents_referred.awc_name_id = awc_name
        adolescents_referred.girls_referred_10_14_year = girls_referred_10_14_year
        adolescents_referred.girls_referred_15_19_year = girls_referred_15_19_year
        adolescents_referred.boys_referred_10_14_year = boys_referred_10_14_year
        adolescents_referred.boys_referred_15_19_year = boys_referred_15_19_year
        adolescents_referred.girls_hwc_referred = girls_hwc_referred
        adolescents_referred.girls_hwc_visited = girls_hwc_visited
        adolescents_referred.girls_afhc_referred = girls_afhc_referred
        adolescents_referred.girls_afhc_visited = girls_afhc_visited
        adolescents_referred.girls_dh_referred = girls_dh_referred
        adolescents_referred.girls_dh_visited = girls_dh_visited
        adolescents_referred.boys_hwc_referred = boys_hwc_referred
        adolescents_referred.boys_hwc_visited = boys_hwc_visited
        adolescents_referred.boys_afhc_referred = boys_afhc_referred
        adolescents_referred.boys_afhc_visited = boys_afhc_visited
        adolescents_referred.boys_dh_referred = boys_dh_referred
        adolescents_referred.boys_dh_visited = boys_dh_visited
        adolescents_referred.task_id = task
        adolescents_referred.site_id =  current_site
        adolescents_referred.save()
        return redirect('/po-report/untrust/adolescent-referred-listing/'+str(task_id))
    return render(request, 'po_report/untrust/adolescent_referred/edit_adolescent_referred.html', locals())


@ login_required(login_url='/login/')
def friendly_club_listing_untrust_po_report(request, task_id):
    heading = "Section 5: Details of Adolescent Friendly Club (AFC)"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(task__id = task_id)
    data = pagination_function(request, friendly_club)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/friendly_club/friendly_club_listing.html', locals())

@ login_required(login_url='/login/')
def add_friendly_club_untrust_po_report(request, task_id):
    heading = "Section 5: Add of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(status=1)
    gramapanchayat = GramaPanchayat.objects.filter(status=1)
    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        panchayat_name_id = data.get('panchayat_name')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)

        friendly_club = AdolescentFriendlyClub.objects.create(start_date = date_of_registration, panchayat_name=panchayat_name,
        hsc_name=hsc_name, subject=subject, facilitator=facilitator, designation=designation,
        no_of_sahiya=no_of_sahiya, no_of_aww=no_of_aww, pe_girls_10_14_year=pe_girls_10_14_year,
        pe_girls_15_19_year=pe_girls_15_19_year, pe_boys_10_14_year=pe_boys_10_14_year,
        pe_boys_15_19_year=pe_boys_15_19_year, task=task, site_id = current_site)
        friendly_club.save()
        return redirect('/cc-report/untrust/friendly-club-listing/'+str(task_id))
    return render(request, 'cc_report/untrust/friendly_club/add_friendly_club.html', locals())



@ login_required(login_url='/login/')
def edit_friendly_club_untrust_po_report(request, friendly_club_id, task_id):
    heading = "Section 5: Edit of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    friendly_club =  AdolescentFriendlyClub.objects.get(id=friendly_club_id)
    gramapanchayat = GramaPanchayat.objects.filter(status=1)
    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        panchayat_name_id = data.get('panchayat_name')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)

        friendly_club.start_date = date_of_registration
        friendly_club.panchayat_name_id = panchayat_name
        friendly_club.hsc_name = hsc_name
        friendly_club.subject = subject
        friendly_club.facilitator = facilitator
        friendly_club.designation = designation
        friendly_club.no_of_sahiya = no_of_sahiya
        friendly_club.no_of_aww = no_of_aww
        friendly_club.pe_girls_10_14_year = pe_girls_10_14_year
        friendly_club.pe_girls_15_19_year = pe_girls_15_19_year
        friendly_club.pe_boys_10_14_year = pe_boys_10_14_year
        friendly_club.pe_boys_15_19_year = pe_boys_15_19_year
        friendly_club.task_id = task
        friendly_club.site_id =  current_site
        friendly_club.save()
        return redirect('/po-report/untrust/friendly-club-listing/'+str(task_id))
    return render(request, 'po_report/untrust/friendly_club/edit_friendly_club.html', locals())

@ login_required(login_url='/login/')
def balsansad_meeting_listing_untrust_po_report(request, task_id):
    heading = "Section 6: Details of Bal Sansad meetings conducted"
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.filter(status=1, school_name__id__in=school_id, task__id = task_id)
    data = pagination_function(request, balsansad_meeting)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/bal_sansad_metting/bal_sansad_listing.html', locals())

@ login_required(login_url='/login/')
def add_balsansad_meeting_untrust_po_report(request, task_id):
    heading = "Section 6: Add of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.filter()
    school = School.objects.filter(status=1, id__in=school_id)
    masterlookups_issues_discussion = MasterLookUp.objects.filter(parent__slug = 'issues_discussion')

    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        school_name_id = data.get('school_name')
        school_name = School.objects.get(id=school_name_id)
        no_of_participants = data.get('no_of_participants')
        decision_taken = data.get('decision_taken')
        issues_discussion = data.get('issues_discussion')
        task = Task.objects.get(id=task_id)
        balsansad_meeting = BalSansadMeeting.objects.create(start_date = date_of_registration, school_name=school_name,
        no_of_participants=no_of_participants, decision_taken=decision_taken,
        task=task, site_id = current_site)
        if issues_discussion:
            issues_discussion = MasterLookUp.objects.get(id=issues_discussion)
            balsansad_meeting.issues_discussion = issues_discussion
        balsansad_meeting.save()
        return redirect('/po-report/untrust/balsansad-listing/'+str(task_id))
    return render(request, 'po_report/untrust/bal_sansad_metting/add_bal_sansad.html', locals())


@ login_required(login_url='/login/')
def edit_balsansad_meeting_untrust_po_report(request, balsansad_id, task_id):
    heading = "Section 6: Edit of Bal Sansad meetings conducted"
    current_site = request.session.get('site_id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    balsansad_meeting =  BalSansadMeeting.objects.get(id=balsansad_id)
    school = School.objects.filter(status=1, id__in=school_id)
    masterlookups_issues_discussion = MasterLookUp.objects.filter(parent__slug = 'issues_discussion')

    if request.method == 'POST':
        data = request.POST
        school_name_id = data.get('school_name')
        school_name = School.objects.get(id=school_name_id)
        no_of_participants = data.get('no_of_participants')
        issues_discussion = data.get('issues_discussion')
        decision_taken = data.get('decision_taken')
        task = Task.objects.get(id=task_id)
        balsansad_meeting.school_name_id = school_name
        balsansad_meeting.no_of_participants = no_of_participants
        balsansad_meeting.decision_taken = decision_taken
        balsansad_meeting.task_id = task
        balsansad_meeting.site_id =  current_site
        if issues_discussion:
            issues_discussion = MasterLookUp.objects.get(id=issues_discussion)
            balsansad_meeting.issues_discussion = issues_discussion
        balsansad_meeting.save()
        return redirect('/po-report/untrust/balsansad-listing/'+str(task_id))
    return render(request, 'po_report/untrust/bal_sansad_metting/edit_bal_sansad.html', locals())


@ login_required(login_url='/login/')
def friendly_club_listing_untrust_po_report(request, task_id):
    heading = "Section 6: Details of Adolescent Friendly Club (AFC)"
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(status=1, panchayat_name__id__in=panchayat_id, task__id = task_id)
    data = pagination_function(request, friendly_club)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/friendly_club/friendly_club_listing.html', locals())

@ login_required(login_url='/login/')
def add_friendly_club_untrust_po_report(request, task_id):
    heading = "Section 6: Add of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.filter(status=1)
    gramapanchayat = GramaPanchayat.objects.filter(status=1, id__in=panchayat_id)
    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        panchayat_name_id = data.get('panchayat_name')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)

        friendly_club = AdolescentFriendlyClub.objects.create(start_date = date_of_registration, panchayat_name=panchayat_name,
        hsc_name=hsc_name, subject=subject, facilitator=facilitator, designation=designation,
        no_of_sahiya=no_of_sahiya, no_of_aww=no_of_aww, pe_girls_10_14_year=pe_girls_10_14_year,
        pe_girls_15_19_year=pe_girls_15_19_year, pe_boys_10_14_year=pe_boys_10_14_year,
        pe_boys_15_19_year=pe_boys_15_19_year, task=task, site_id = current_site)
        friendly_club.save()
        return redirect('/po-report/untrust/friendly-club-listing/'+str(task_id))
    return render(request, 'po_report/untrust/friendly_club/add_friendly_club.html', locals())



@ login_required(login_url='/login/')
def edit_friendly_club_untrust_po_report(request, friendly_club_id, task_id):
    heading = "Section 6: Details of Adolescent Friendly Club (AFC)"
    current_site = request.session.get('site_id')
    panchayat_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__id')
    friendly_club =  AdolescentFriendlyClub.objects.get(id=friendly_club_id)
    gramapanchayat = GramaPanchayat.objects.filter(status=1, id__in=panchayat_id)
    if request.method == 'POST':
        data = request.POST
        date_of_registration = data.get('date_of_registration')
        panchayat_name_id = data.get('panchayat_name')
        panchayat_name = GramaPanchayat.objects.get(id=panchayat_name_id)
        hsc_name = data.get('hsc_name')
        subject = data.get('subject')
        facilitator = data.get('facilitator')
        designation = data.get('designation')
        no_of_sahiya = data.get('no_of_sahiya')
        no_of_aww = data.get('no_of_aww')
        pe_girls_10_14_year = data.get('pe_girls_10_14_year')
        pe_girls_15_19_year = data.get('pe_girls_15_19_year')
        pe_boys_10_14_year = data.get('pe_boys_10_14_year')
        pe_boys_15_19_year = data.get('pe_boys_15_19_year')
        task = Task.objects.get(id=task_id)

        friendly_club.start_date = date_of_registration
        friendly_club.panchayat_name_id = panchayat_name
        friendly_club.hsc_name = hsc_name
        friendly_club.subject = subject
        friendly_club.facilitator = facilitator
        friendly_club.designation = designation
        friendly_club.no_of_sahiya = no_of_sahiya
        friendly_club.no_of_aww = no_of_aww
        friendly_club.pe_girls_10_14_year = pe_girls_10_14_year
        friendly_club.pe_girls_15_19_year = pe_girls_15_19_year
        friendly_club.pe_boys_10_14_year = pe_boys_10_14_year
        friendly_club.pe_boys_15_19_year = pe_boys_15_19_year
        friendly_club.task_id = task
        friendly_club.site_id =  current_site
        friendly_club.save()
        return redirect('/po-report/untrust/friendly-club-listing/'+str(task_id))
    return render(request, 'po_report/untrust/friendly_club/edit_friendly_club.html', locals())


@ login_required(login_url='/login/')
def community_activities_listing_untrust_po_report(request, task_id):
    heading = "Section 7: Details of community engagement activities"
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.filter(status=1, village_name__id__in=village_id, task__id = task_id)
    data = pagination_function(request, activities)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/community_activities/community_activities_listing.html', locals())


@ login_required(login_url='/login/')
def add_community_activities_untrust_po_report(request, task_id):
    heading = "Section 7: Add of community engagement activities"
    current_site = request.session.get('site_id')
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.filter(status=1,)
    village =  Village.objects.filter(status=1, id__in=village_id)

    masterlookups_event = MasterLookUp.objects.filter(parent__slug = 'event')
    masterlookups_activity = MasterLookUp.objects.filter(parent__slug = 'activities')

    if request.method == 'POST':
        data = request.POST
        village_name_id = data.get('village_name')
        date_of_registration = data.get('date_of_registration')
        village_name = Village.objects.get(id=village_name_id)
        name_of_event_activity = data.get('name_of_event_activity')
        name_of_event_id = data.get('name_of_event')
        name_of_activity_id = data.get('name_of_activity')
        organized_by = data.get('organized_by')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)

        activities =  CommunityEngagementActivities.objects.create(village_name=village_name, start_date = date_of_registration,
        name_of_event_activity=name_of_event_activity, organized_by=organized_by,
        girls_10_14_year=girls_10_14_year, girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year,
        boys_15_19_year=boys_15_19_year, champions_15_19_year=champions_15_19_year, adult_male=adult_male,
        adult_female=adult_female, teachers=teachers, pri_members=pri_members, services_providers=services_providers,
        sms_members=sms_members, other=other, task=task, site_id = current_site)
        
        if name_of_event_id:
            name_of_event = MasterLookUp.objects.get(id = name_of_event_id)
            activities.event_name = name_of_event

        if name_of_activity_id:
            name_of_activity = MasterLookUp.objects.get(id = name_of_activity_id)
            activities.activity_name = name_of_activity
        activities.save()
        return redirect('/po-report/untrust/community-activities-listing/'+str(task_id))
    return render(request, 'po_report/untrust/community_activities/add_community_activities.html', locals())


@ login_required(login_url='/login/')
def edit_community_activities_untrust_po_report(request, activities_id, task_id):
    heading = "Section 7: Edit of community engagement activities"
    current_site = request.session.get('site_id')
    village_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    activities =  CommunityEngagementActivities.objects.get(id=activities_id)
    village =  Village.objects.filter(status=1, id__in=village_id)
    masterlookups_event = MasterLookUp.objects.filter(parent__slug = 'event')
    masterlookups_activity = MasterLookUp.objects.filter(parent__slug = 'activities')

    if request.method == 'POST':
        data = request.POST
        village_name_id = data.get('village_name')
        date_of_registration = data.get('date_of_registration')
        village_name = Village.objects.get(id=village_name_id)
        name_of_event_activity = data.get('name_of_event_activity')
        # theme_topic = data.get('theme_topic')
        name_of_event_id = data.get('name_of_event')
        name_of_activity_id = data.get('name_of_activity')

        organized_by = data.get('organized_by')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)

        activities.start_date = date_of_registration
        activities.village_name_id = village_name
        activities.name_of_event_activity = name_of_event_activity
        # activities.theme_topic = theme_topic
        activities.organized_by = organized_by
        activities.boys_10_14_year = boys_10_14_year
        activities.boys_15_19_year = boys_15_19_year
        activities.girls_10_14_year = girls_10_14_year
        activities.girls_15_19_year = girls_15_19_year
        activities.champions_15_19_year = champions_15_19_year
        activities.adult_male = adult_male
        activities.adult_female = adult_female
        activities.teachers = teachers
        activities.pri_members = pri_members
        activities.services_providers = services_providers
        activities.sms_members = sms_members
        activities.other = other
        activities.task_id = task
        activities.site_id =  current_site
        
        if name_of_event_id:
            name_of_event = MasterLookUp.objects.get(id = name_of_event_id)
            activities.event_name = name_of_event

        if name_of_activity_id:
            name_of_activity = MasterLookUp.objects.get(id = name_of_activity_id)
            activities.activity_name = name_of_activity
        activities.save()
        return redirect('/po-report/untrust/community-activities-listing/'+str(task_id))
    return render(request, 'po_report/untrust/community_activities/edit_community_activities.html', locals())

@ login_required(login_url='/login/')
def champions_listing_untrust_po_report(request, task_id):
    heading = "Section 8: Details of exposure visits of adolescent champions"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.filter(status=1, awc_name__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, champions)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/champions/champions_listing.html', locals())




@ login_required(login_url='/login/')
def add_champions_untrust_po_report(request, task_id):
    heading = "Section 8: Add of exposure visits of adolescent champions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.filter()
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        date_of_visit = data.get('date_of_visit')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        first_inst_visited = data.get('first_inst_visited')
        second_inst_visited = data.get('second_inst_visited')
        third_inst_visited = data.get('third_inst_visited')
        fourth_inst_visited = data.get('fourth_inst_visited')
        task = Task.objects.get(id=task_id)

        champions =  Champions.objects.create(awc_name=awc_name, date_of_visit=date_of_visit, girls_10_14_year=girls_10_14_year,
        girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year, boys_15_19_year=boys_15_19_year,
        first_inst_visited=first_inst_visited,second_inst_visited=second_inst_visited or None,
        third_inst_visited=third_inst_visited or None, fourth_inst_visited=fourth_inst_visited or None, task=task, site_id = current_site)
        champions.save()
        return redirect('/po-report/untrust/champions-listing/'+str(task_id))
    return render(request, 'po_report/untrust/champions/add_champions.html', locals())


@ login_required(login_url='/login/')
def edit_champions_untrust_po_report(request, champions_id, task_id):
    heading = "Section 8: Edit of exposure visits of adolescent champions"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    champions =  Champions.objects.get(id=champions_id)
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        date_of_visit = data.get('date_of_visit')
        awc_name = AWC.objects.get(id=awc_name_id)
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        first_inst_visited = data.get('first_inst_visited')
        second_inst_visited = data.get('second_inst_visited')
        third_inst_visited = data.get('third_inst_visited')
        fourth_inst_visited = data.get('fourth_inst_visited')
        task = Task.objects.get(id=task_id)

        champions.awc_name_id = awc_name   
        champions.date_of_visit = date_of_visit     
        champions.girls_10_14_year = girls_10_14_year       
        champions.girls_15_19_year = girls_15_19_year     
        champions.boys_10_14_year = boys_10_14_year       
        champions.boys_15_19_year = boys_15_19_year       
        champions.first_inst_visited = first_inst_visited
        champions.second_inst_visited= second_inst_visited or None
        champions.third_inst_visited = third_inst_visited or None
        champions.fourth_inst_visited = fourth_inst_visited or None
        champions.task_id = task
        champions.site_id =  current_site       
        champions.save()
        return redirect('/po-report/untrust/champions-listing/'+str(task_id))
    return render(request, 'po_report/untrust/champions/edit_champions.html', locals())

@ login_required(login_url='/login/')
def reenrolled_listing_untrust_po_report(request, task_id):
    heading = "Section 9: Details of adolescent re-enrolled in schools"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, adolescent_reenrolled)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/re_enrolled/re_enrolled_listing.html', locals())

@ login_required(login_url='/login/')
def add_reenrolled_untrust_po_report(request, task_id):
    heading = "Section 9: Add of adolescent re-enrolled in schools"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.filter()
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    # school = School.objects.filter(status=1, id__in = school_id)
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        gender = data.get('gender')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        school_name = data.get('school_name')
        # school_name = School.objects.get(id=school_name_id)
        which_class_enrolled = data.get('which_class_enrolled')
        task = Task.objects.get(id=task_id)

        adolescent_reenrolled =  AdolescentRe_enrolled.objects.create(adolescent_name=adolescent_name,
        gender=gender, age=age, parent_guardian_name=parent_guardian_name, school_name=school_name, which_class_enrolled=which_class_enrolled,
        task=task, site_id = current_site)
        adolescent_reenrolled.save()
        return redirect('/po-report/untrust/reenrolled-listing/'+str(task_id))
    return render(request, 'po_report/untrust/re_enrolled/add_re_enrolled.html', locals())


@ login_required(login_url='/login/')
def edit_reenrolled_untrust_po_report(request, reenrolled_id, task_id):
    heading = "Section 9: Edit of adolescent re-enrolled in schools"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    adolescent_reenrolled =  AdolescentRe_enrolled.objects.get(id=reenrolled_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    # school = School.objects.filter()
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        gender = data.get('gender')
        age = data.get('age')
        parent_guardian_name = data.get('parent_guardian_name')
        school_name = data.get('school_name')
        # school_name = School.objects.get(id=school_name_id)
        which_class_enrolled = data.get('which_class_enrolled')
        task = Task.objects.get(id=task_id)

        adolescent_reenrolled.adolescent_name_id = adolescent_name
        adolescent_reenrolled.gender = gender
        adolescent_reenrolled.age = age
        adolescent_reenrolled.parent_guardian_name = parent_guardian_name
        adolescent_reenrolled.school_name = school_name
        adolescent_reenrolled.which_class_enrolled = which_class_enrolled
        adolescent_reenrolled.task_id = task
        adolescent_reenrolled.site_id =  current_site
        adolescent_reenrolled.save()
        return redirect('/po-report/untrust/reenrolled-listing/'+str(task_id))
    return render(request, 'po_report/untrust/re_enrolled/edit_re_enrolled.html', locals())

@ login_required(login_url='/login/')
def vlcpc_meeting_listing_untrust_po_report(request, task_id):
    heading = "Section 10: Details of VLCPC meetings"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vlcpc_metting =  VLCPCMetting.objects.filter(status=1, awc_name__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, vlcpc_metting)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/vlcpc_meetings/vlcpc_meeting_listing.html', locals())

@ login_required(login_url='/login/')
def add_vlcpc_meeting_untrust_po_report(request, task_id):
    heading = "Section 10: Add of VLCPC meetings"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vlcpc_metting =  VLCPCMetting.objects.filter()
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        date_of_meeting = data.get('date_of_meeting')
        issues_discussed = data.get('issues_discussed')
        decision_taken = data.get('decision_taken')
        no_of_participants_planned = data.get('no_of_participants_planned')
        no_of_participants_attended = data.get('no_of_participants_attended')
        task = Task.objects.get(id=task_id)

        vlcpc_metting = VLCPCMetting.objects.create(awc_name=awc_name, date_of_meeting=date_of_meeting,
        issues_discussed=issues_discussed, decision_taken=decision_taken, no_of_participants_planned=no_of_participants_planned,
        no_of_participants_attended=no_of_participants_attended, task=task, site_id = current_site)
        vlcpc_metting.save()
        return redirect('/po-report/untrust/vlcpc-meeting-listing/'+str(task_id))
    return render(request, 'po_report/untrust/vlcpc_meetings/add_vlcpc_meeting.html', locals())


@ login_required(login_url='/login/')
def edit_vlcpc_meeting_untrust_po_report(request, vlcpc_metting, task_id):
    heading = "Section 10: Edit of VLCPC meetings"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    vlcpc_metting =  VLCPCMetting.objects.get(id=vlcpc_metting)
    awc =  AWC.objects.filter(status=1, id__in=awc_id)
    if request.method == 'POST':
        data = request.POST
        awc_name_id = data.get('awc_name')
        awc_name = AWC.objects.get(id=awc_name_id)
        date_of_meeting = data.get('date_of_meeting')
        issues_discussed = data.get('issues_discussed')
        decision_taken = data.get('decision_taken')
        no_of_participants_planned = data.get('no_of_participants_planned')
        no_of_participants_attended = data.get('no_of_participants_attended')
        task = Task.objects.get(id=task_id)

        vlcpc_metting.awc_name_id = awc_name
        vlcpc_metting.date_of_meeting = date_of_meeting
        vlcpc_metting.issues_discussed = issues_discussed
        vlcpc_metting.decision_taken = decision_taken
        vlcpc_metting.no_of_participants_planned = no_of_participants_planned
        vlcpc_metting.no_of_participants_attended = no_of_participants_attended
        vlcpc_metting.task_id = task
        vlcpc_metting.site_id =  current_site
        vlcpc_metting.save()
        return redirect('/po-report/untrust/vlcpc-meeting-listing/'+str(task_id))
    return render(request, 'po_report/untrust/vlcpc_meetings/edit_vlcpc_meeting.html', locals())


@ login_required(login_url='/login/')
def dcpu_bcpu_listing_untrust_po_report(request, task_id):
    heading = "Section 11: Details of DCPU/BCPU engagement at community and institutional level"
    block_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__block__id')
    dcpu_bcpu = DCPU_BCPU.objects.filter(status=1, block_name__id__in=block_id, task__id = task_id)
    data = pagination_function(request, dcpu_bcpu)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/dcpu_bcpu/dcpu_bcpu_listing.html', locals())

@ login_required(login_url='/login/')
def add_dcpu_bcpu_untrust_po_report(request, task_id):
    heading = "Section 11: Add of DCPU/BCPU engagement at community and institutional level"
    current_site = request.session.get('site_id')
    block_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__block__id')
    dcpu_bcpu = DCPU_BCPU.objects.filter(status=1)
    block_obj = Block.objects.filter(status=1, id__in=block_id)
    if request.method == 'POST':
        data = request.POST
        block_name_id = data.get('block_name')
        block_name = Block.objects.get(id=block_name_id)
        name_of_institution = data.get('name_of_institution')
        date_of_visit = data.get('date_of_visit')
        name_of_lead = data.get('name_of_lead')
        designation = data.get('designation')
        issues_discussed = data.get('issues_discussed')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)
        
        dcpu_bcpu = DCPU_BCPU.objects.create(block_name=block_name, name_of_institution=name_of_institution,
        date_of_visit=date_of_visit, name_of_lead=name_of_lead, designation=designation, issues_discussed=issues_discussed,
        girls_10_14_year=girls_10_14_year, girls_15_19_year=girls_15_19_year, boys_10_14_year=boys_10_14_year,
        boys_15_19_year=boys_15_19_year, champions_15_19_year=champions_15_19_year,
        adult_male=adult_male, adult_female=adult_female, teachers=teachers, pri_members=pri_members, 
        services_providers=services_providers, sms_members=sms_members, other=other,
        task=task, site_id = current_site)
        dcpu_bcpu.save()
        return redirect('/po-report/untrust/dcpu-bcpu-listing/'+str(task_id))
    return render(request, 'po_report/untrust/dcpu_bcpu/add_dcpu_bcpu.html', locals())



@ login_required(login_url='/login/')
def edit_dcpu_bcpu_untrust_po_report(request, dcpu_bcpu_id, task_id):
    heading = "Section 11: Edit of DCPU/BCPU engagement at community and institutional level"
    current_site = request.session.get('site_id')
    block_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__grama_panchayat__block__id')
    dcpu_bcpu = DCPU_BCPU.objects.get(id=dcpu_bcpu_id)
    block_obj = Block.objects.filter(status=1, id__in=block_id)
    if request.method == 'POST':
        data = request.POST
        block_name_id = data.get('block_name')
        block_name = Block.objects.get(id=block_name_id)
        name_of_institution = data.get('name_of_institution')
        date_of_visit = data.get('date_of_visit')
        name_of_lead = data.get('name_of_lead')
        designation = data.get('designation')
        issues_discussed = data.get('issues_discussed')
        girls_10_14_year = data.get('girls_10_14_year')
        girls_15_19_year = data.get('girls_15_19_year')
        boys_10_14_year = data.get('boys_10_14_year')
        boys_15_19_year = data.get('boys_15_19_year')
        champions_15_19_year = data.get('champions_15_19_year')
        adult_male = data.get('adult_male')
        adult_female = data.get('adult_female')
        teachers = data.get('teachers')
        pri_members = data.get('pri_members')
        services_providers = data.get('services_providers')
        sms_members = data.get('sms_members')
        other = data.get('other')
        task = Task.objects.get(id=task_id)


        dcpu_bcpu.block_name_id = block_name
        dcpu_bcpu.name_of_institution = name_of_institution 
        dcpu_bcpu.date_of_visit = date_of_visit 
        dcpu_bcpu.name_of_lead = name_of_lead 
        dcpu_bcpu.designation = designation 
        dcpu_bcpu.issues_discussed = issues_discussed 
        dcpu_bcpu.girls_10_14_year = girls_10_14_year 
        dcpu_bcpu.girls_15_19_year = girls_15_19_year 
        dcpu_bcpu.boys_10_14_year = boys_10_14_year 
        dcpu_bcpu.boys_15_19_year = boys_15_19_year 
        dcpu_bcpu.champions_15_19_year = champions_15_19_year 
        dcpu_bcpu.adult_male = adult_male 
        dcpu_bcpu.adult_female = adult_female 
        dcpu_bcpu.teachers = teachers 
        dcpu_bcpu.pri_members = pri_members 
        dcpu_bcpu.services_providers = services_providers 
        dcpu_bcpu.sms_members = sms_members 
        dcpu_bcpu.other = other 
        dcpu_bcpu.task_id = task 
        dcpu_bcpu.site_id =  current_site 
        dcpu_bcpu.save()
        return redirect('/po-report/untrust/dcpu-bcpu-listing/'+str(task_id))
    return render(request, 'po_report/untrust/dcpu_bcpu/edit_dcpu_bcpu.html', locals())


@ login_required(login_url='/login/')
def educational_enrichment_listing_untrust_po_report(request, task_id):
    heading = "Section 12: Details of educational enrichment support provided"
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    education_enrichment =  EducatinalEnrichmentSupportProvided.objects.filter(status=1, adolescent_name__awc__id__in=awc_id, task__id = task_id)
    data = pagination_function(request, education_enrichment)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/educational_enrichment/educational_enrichment_listing.html', locals())



@ login_required(login_url='/login/')
def add_educational_enrichment_untrust_po_report(request, task_id):
    heading = "Section 12: Add of educational enrichment support provided"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    education_enrichment =  EducatinalEnrichmentSupportProvided.objects.filter(status=1, )
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        parent_guardian_name = data.get('parent_guardian_name')
        enrolment_date = data.get('enrolment_date')
        standard = data.get('standard')
        duration_of_coaching_support = data.get('duration_of_coaching_support')
        task = Task.objects.get(id=task_id)
        education_enrichment =  EducatinalEnrichmentSupportProvided.objects.create(adolescent_name=adolescent_name,
        parent_guardian_name=parent_guardian_name, standard=standard, enrolment_date=enrolment_date,
        duration_of_coaching_support=duration_of_coaching_support, task=task, site_id = current_site)
        education_enrichment.save()
        return redirect('/po-report/untrust/educational-enrichment-listing/'+str(task_id))
    return render(request, 'po_report/untrust/educational_enrichment/add_educational_enrichment.html', locals())


@ login_required(login_url='/login/')
def edit_educational_enrichment_untrust_po_report(request, educational_id, task_id):
    heading = "Section 12: Edit of educational enrichment support provided"
    current_site = request.session.get('site_id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    education_enrichment =  EducatinalEnrichmentSupportProvided.objects.get(id=educational_id)
    adolescent_obj =  Adolescent.objects.filter(status=1, awc__id__in=awc_id, site=current_site)
    if request.method == 'POST':
        data = request.POST
        adolescent_name_id = data.get('adolescent_name')
        adolescent_name = Adolescent.objects.get(id=adolescent_name_id, site=current_site)
        parent_guardian_name = data.get('parent_guardian_name')
        enrolment_date = data.get('enrolment_date')
        standard = data.get('standard')
        duration_of_coaching_support = data.get('duration_of_coaching_support')
        task = Task.objects.get(id=task_id)

        education_enrichment.adolescent_name_id = adolescent_name
        education_enrichment.parent_guardian_name = parent_guardian_name
        education_enrichment.enrolment_date = enrolment_date
        education_enrichment.standard = standard
        education_enrichment.duration_of_coaching_support = duration_of_coaching_support
        education_enrichment.task_id = task
        education_enrichment.site_id =  current_site
        education_enrichment.save()
        return redirect('/po-report/untrust/educational-enrichment-listing/'+str(task_id))
    return render(request, 'po_report/untrust/educational_enrichment/edit_educational_enrichment.html', locals())


@ login_required(login_url='/login/')
def stakeholders_listing_untrust_po_report(request, task_id):
    heading = "Section 13: Details of capacity building of different stakeholders"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    if Stakeholder.objects.filter(task=task_id).exists():
        error="disabled"
    stakeholders_obj = Stakeholder.objects.filter(user_name=request.user.id, task__id = task_id)
    data = pagination_function(request, stakeholders_obj)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/stakeholders/stakeholders_listing.html', locals())


@ login_required(login_url='/login/')
def add_stakeholders_untrust_po_report(request, task_id):
    heading = "Section 13: Add of capacity building of different stakeholders"
    current_site = request.session.get('site_id')
    stakeholders_obj = Stakeholder.objects.filter()
    if request.method == 'POST':
        data = request.POST
        master_trainers_male = data.get('master_trainers_male')
        master_trainers_female = data.get('master_trainers_female')
        master_trainers_total = data.get('master_trainers_total')
        nodal_teachers_male = data.get('nodal_teachers_male')
        nodal_teachers_female = data.get('nodal_teachers_female')
        nodal_teachers_total = data.get('nodal_teachers_total')
        principals_male = data.get('principals_male')
        principals_female = data.get('principals_female')
        principals_total = data.get('principals_total')
        district_level_officials_male = data.get('district_level_officials_male')
        district_level_officials_female = data.get('district_level_officials_female')
        district_level_officials_total = data.get('district_level_officials_total')
        peer_educator_male = data.get('peer_educator_male')
        peer_educator_female = data.get('peer_educator_female')
        peer_educator_total = data.get('peer_educator_total')
        state_level_officials_male = data.get('state_level_officials_male')
        state_level_officials_female = data.get('state_level_officials_female')
        state_level_officials_total = data.get('state_level_officials_total')
        icds_awws_male = data.get('icds_awws_male')
        icds_awws_female = data.get('icds_awws_female')
        icds_awws_total = data.get('icds_awws_total')
        icds_supervisors_male = data.get('icds_supervisors_male')
        icds_supervisors_female = data.get('icds_supervisors_female')
        icds_supervisors_total = data.get('icds_supervisors_total')
        icds_peer_educator_male = data.get('icds_peer_educator_male')
        icds_peer_educator_female = data.get('icds_peer_educator_female')
        icds_peer_educator_total = data.get('icds_peer_educator_total')
        icds_child_developement_project_officers_male = data.get('icds_child_developement_project_officers_male')
        icds_child_developement_project_officers_female = data.get('icds_child_developement_project_officers_female')
        icds_child_developement_project_officers_total = data.get('icds_child_developement_project_officers_total')
        icds_district_level_officials_male = data.get('icds_district_level_officials_male')
        icds_district_level_officials_female = data.get('icds_district_level_officials_female')
        icds_district_level_officials_total = data.get('icds_district_level_officials_total')
        icds_state_level_officials_male = data.get('icds_state_level_officials_male')
        icds_state_level_officials_female = data.get('icds_state_level_officials_female')
        icds_state_level_officials_total = data.get('icds_state_level_officials_total')
        health_ashas_male = data.get('health_ashas_male')
        health_ashas_female = data.get('health_ashas_female')
        health_ashas_total = data.get('health_ashas_total')
        health_anms_male = data.get('health_anms_male')
        health_anms_female = data.get('health_anms_female')
        health_anms_total = data.get('health_anms_total')
        health_bpm_bhm_pheos_male = data.get('health_bpm_bhm_pheos_male')
        health_bpm_bhm_pheos_female = data.get('health_bpm_bhm_pheos_female')
        health_bpm_bhm_pheos_total = data.get('health_bpm_bhm_pheos_total')
        health_medical_officers_male = data.get('health_medical_officers_male')
        health_medical_officers_female = data.get('health_medical_officers_female')
        health_medical_officers_total = data.get('health_medical_officers_total')
        health_district_level_officials_male = data.get('health_district_level_officials_male')
        health_district_level_officials_female = data.get('health_district_level_officials_female')
        health_district_level_officials_total = data.get('health_district_level_officials_total')
        health_state_level_officials_male = data.get('health_state_level_officials_male')
        health_state_level_officials_female = data.get('health_state_level_officials_female')
        health_state_level_officials_total = data.get('health_state_level_officials_total')
        health_rsk_male = data.get('health_rsk_male')
        health_rsk_female = data.get('health_rsk_female')
        health_rsk_total = data.get('health_rsk_total')
        health_peer_educator_male = data.get('health_peer_educator_male')
        health_peer_educator_female = data.get('health_peer_educator_female')
        health_peer_educator_total = data.get('health_peer_educator_total')
        panchayat_ward_members_male = data.get('panchayat_ward_members_male')
        panchayat_ward_members_female = data.get('panchayat_ward_members_female')
        panchayat_ward_members_total = data.get('panchayat_ward_members_total')
        panchayat_up_mukhiya_up_Pramukh_male = data.get('panchayat_up_mukhiya_up_Pramukh_male')
        panchayat_up_mukhiya_up_Pramukh_female = data.get('panchayat_up_mukhiya_up_Pramukh_female')
        panchayat_up_mukhiya_up_Pramukh_total = data.get('panchayat_up_mukhiya_up_Pramukh_total')
        panchayat_mukhiya_Pramukh_male = data.get('panchayat_mukhiya_Pramukh_male')
        panchayat_mukhiya_Pramukh_female = data.get('panchayat_mukhiya_Pramukh_female')
        panchayat_mukhiya_Pramukh_total = data.get('panchayat_mukhiya_Pramukh_total')
        panchayat_samiti_member_male = data.get('panchayat_samiti_member_male')
        panchayat_samiti_member_female = data.get('panchayat_samiti_member_female')
        panchayat_samiti_member_total = data.get('panchayat_samiti_member_total')
        panchayat_zila_parishad_member_male = data.get('panchayat_zila_parishad_member_male')
        panchayat_zila_parishad_member_female = data.get('panchayat_zila_parishad_member_female')
        panchayat_zila_parishad_member_total = data.get('panchayat_zila_parishad_member_total')
        panchayat_vc_zila_parishad_male = data.get('panchayat_vc_zila_parishad_male')
        panchayat_vc_zila_parishad_female = data.get('panchayat_vc_zila_parishad_female')
        panchayat_vc_zila_parishad_total = data.get('panchayat_vc_zila_parishad_total')
        panchayat_chairman_zila_parishad_male = data.get('panchayat_chairman_zila_parishad_male')
        panchayat_chairman_zila_parishad_female = data.get('panchayat_chairman_zila_parishad_female')
        panchayat_chairman_zila_parishad_total = data.get('panchayat_chairman_zila_parishad_total')
        panchayat_block_level_officials_male = data.get('panchayat_block_level_officials_male')
        panchayat_block_level_officials_female = data.get('panchayat_block_level_officials_female')
        panchayat_block_level_officials_total = data.get('panchayat_block_level_officials_total')
        panchayat_district_level_officials_male = data.get('panchayat_district_level_officials_male')
        panchayat_district_level_officials_female = data.get('panchayat_district_level_officials_female')
        panchayat_district_level_officials_total = data.get('panchayat_district_level_officials_total')
        panchayat_state_level_officials_male = data.get('panchayat_state_level_officials_male')
        panchayat_state_level_officials_female = data.get('panchayat_state_level_officials_female')
        panchayat_state_level_officials_total = data.get('panchayat_state_level_officials_total')
        media_interns_male = data.get('media_interns_male')
        media_interns_female = data.get('media_interns_female')
        media_interns_total = data.get('media_interns_total')
        media_journalists_male = data.get('media_journalists_male')
        media_journalists_female = data.get('media_journalists_female')
        media_journalists_total = data.get('media_journalists_total')
        media_editors_male = data.get('media_editors_male')
        media_editors_female = data.get('media_editors_female')
        media_editors_total = data.get('media_editors_total')
        others_block_cluster_field_corrdinators_male = data.get('others_block_cluster_field_corrdinators_male')
        others_block_cluster_field_corrdinators_female = data.get('others_block_cluster_field_corrdinators_female')
        others_block_cluster_field_corrdinators_total = data.get('others_block_cluster_field_corrdinators_total')
        others_ngo_staff_corrdinators_male = data.get('others_ngo_staff_corrdinators_male')
        others_ngo_staff_corrdinators_female = data.get('others_ngo_staff_corrdinators_female')
        others_ngo_staff_corrdinators_total = data.get('others_ngo_staff_corrdinators_total')
        others_male = data.get('others_male')
        others_female = data.get('others_female')
        others_total = data.get('others_total')
        total_male = data.get('total_male')
        total_female = data.get('total_female')
        total = data.get('total')
        task = Task.objects.get(id=task_id)

        if total and int(total) != 0:
            stakeholders_obj = Stakeholder.objects.create(user_name=request.user,
            master_trainers_male=master_trainers_male or None, master_trainers_female=master_trainers_female or None, master_trainers_total=master_trainers_total or None,
            nodal_teachers_male=nodal_teachers_male or None, nodal_teachers_female=nodal_teachers_female or None, nodal_teachers_total=nodal_teachers_total or None,
            principals_male=principals_male or None, principals_female=principals_female or None, principals_total=principals_total or None, 
            district_level_officials_male=district_level_officials_male or None, district_level_officials_female=district_level_officials_female or None, district_level_officials_total=district_level_officials_total or None,
            peer_educator_male=peer_educator_male or None, peer_educator_female=peer_educator_female or None, peer_educator_total=peer_educator_total or None,
            state_level_officials_male=state_level_officials_male or None, state_level_officials_female=state_level_officials_female or None, state_level_officials_total=state_level_officials_total or None,
            icds_awws_male=icds_awws_male or None, icds_awws_female=icds_awws_female or None, icds_awws_total=icds_awws_total or None,
            icds_supervisors_male=icds_supervisors_male or None, icds_supervisors_female=icds_supervisors_female or None, icds_supervisors_total=icds_supervisors_total or None,
            icds_peer_educator_male=icds_peer_educator_male or None, icds_peer_educator_female=icds_peer_educator_female or None, icds_peer_educator_total=icds_peer_educator_total or None,
            icds_child_developement_project_officers_male=icds_child_developement_project_officers_male or None, icds_child_developement_project_officers_female=icds_child_developement_project_officers_female or None, icds_child_developement_project_officers_total=icds_child_developement_project_officers_total or None,
            icds_district_level_officials_male=icds_district_level_officials_male or None, icds_district_level_officials_female=icds_district_level_officials_female or None, icds_district_level_officials_total=icds_district_level_officials_total or None,
            icds_state_level_officials_male=icds_state_level_officials_male or None, icds_state_level_officials_female=icds_state_level_officials_female or None, icds_state_level_officials_total=icds_state_level_officials_total or None,
            health_ashas_male=health_ashas_male or None, health_ashas_female=health_ashas_female or None, health_ashas_total=health_ashas_total or None,
            health_anms_male=health_anms_male or None, health_anms_female=health_anms_female or None, health_anms_total=health_anms_total or None,
            health_bpm_bhm_pheos_male=health_bpm_bhm_pheos_male or None, health_bpm_bhm_pheos_female=health_bpm_bhm_pheos_female or None, health_bpm_bhm_pheos_total=health_bpm_bhm_pheos_total or None,
            health_medical_officers_male=health_medical_officers_male or None, health_medical_officers_female=health_medical_officers_female or None, health_medical_officers_total=health_medical_officers_total or None,
            health_district_level_officials_male=health_district_level_officials_male or None, health_district_level_officials_female=health_district_level_officials_female or None, health_district_level_officials_total=health_district_level_officials_total or None,
            health_state_level_officials_male=health_state_level_officials_male or None, health_state_level_officials_female=health_state_level_officials_female or None, health_state_level_officials_total=health_state_level_officials_total or None,
            health_rsk_male=health_rsk_male or None, health_rsk_female=health_rsk_female or None, health_rsk_total=health_rsk_total or None,
            health_peer_educator_male=health_peer_educator_male or None, health_peer_educator_female=health_peer_educator_female or None, health_peer_educator_total=health_peer_educator_total or None,
            panchayat_ward_members_male=panchayat_ward_members_male or None, panchayat_ward_members_female=panchayat_ward_members_female or None, panchayat_ward_members_total=panchayat_ward_members_total or None,
            panchayat_up_mukhiya_up_Pramukh_male=panchayat_up_mukhiya_up_Pramukh_male or None, panchayat_up_mukhiya_up_Pramukh_female=panchayat_up_mukhiya_up_Pramukh_female or None, panchayat_up_mukhiya_up_Pramukh_total=panchayat_up_mukhiya_up_Pramukh_total or None,
            panchayat_mukhiya_Pramukh_male=panchayat_mukhiya_Pramukh_male or None, panchayat_mukhiya_Pramukh_female=panchayat_mukhiya_Pramukh_female or None, panchayat_mukhiya_Pramukh_total=panchayat_mukhiya_Pramukh_total or None,
            panchayat_samiti_member_male=panchayat_samiti_member_male or None, panchayat_samiti_member_female=panchayat_samiti_member_female or None, panchayat_samiti_member_total=panchayat_samiti_member_total or None,
            panchayat_zila_parishad_member_male=panchayat_zila_parishad_member_male or None, panchayat_zila_parishad_member_female=panchayat_zila_parishad_member_female or None, panchayat_zila_parishad_member_total=panchayat_zila_parishad_member_total or None,
            panchayat_vc_zila_parishad_male=panchayat_vc_zila_parishad_male or None, panchayat_vc_zila_parishad_female=panchayat_vc_zila_parishad_female or None, panchayat_vc_zila_parishad_total=panchayat_vc_zila_parishad_total or None,
            panchayat_chairman_zila_parishad_male=panchayat_chairman_zila_parishad_male or None, panchayat_chairman_zila_parishad_female=panchayat_chairman_zila_parishad_female or None, panchayat_chairman_zila_parishad_total=panchayat_chairman_zila_parishad_total or None,
            panchayat_block_level_officials_male=panchayat_block_level_officials_male or None, panchayat_block_level_officials_female=panchayat_block_level_officials_female or None, panchayat_block_level_officials_total=panchayat_block_level_officials_total or None,
            panchayat_district_level_officials_male=panchayat_district_level_officials_male or None, panchayat_district_level_officials_female=panchayat_district_level_officials_female or None, panchayat_district_level_officials_total=panchayat_district_level_officials_total or None,
            panchayat_state_level_officials_male=panchayat_state_level_officials_male or None, panchayat_state_level_officials_female=panchayat_state_level_officials_female or None, panchayat_state_level_officials_total=panchayat_state_level_officials_total or None,
            media_interns_male=media_interns_male or None, media_interns_female=media_interns_female or None, media_interns_total=media_interns_total or None,
            media_journalists_male=media_journalists_male or None, media_journalists_female=media_journalists_female or None, media_journalists_total=media_journalists_total or None,
            media_editors_male=media_editors_male or None, media_editors_female=media_editors_female or None, media_editors_total=media_editors_total or None,
            others_block_cluster_field_corrdinators_male=others_block_cluster_field_corrdinators_male or None, others_block_cluster_field_corrdinators_female=others_block_cluster_field_corrdinators_female or None, others_block_cluster_field_corrdinators_total=others_block_cluster_field_corrdinators_total or None,
            others_ngo_staff_corrdinators_male=others_ngo_staff_corrdinators_male or None, others_ngo_staff_corrdinators_female=others_ngo_staff_corrdinators_female or None, others_ngo_staff_corrdinators_total=others_ngo_staff_corrdinators_total or None,
            others_male=others_male or None, others_female=others_female or None, others_total=others_total or None,
            total_male=total_male or None, total_female=total_female or None, total=total, task=task, site_id = current_site,
            )
            stakeholders_obj.save()
            return redirect('/po-report/rnp/stakeholders-listing/'+str(task_id))
        else:
            error_message = 'Please, Enter the any one Category of participants for Achieved in this month'
    return render(request, 'po_report/untrust/stakeholders/add_stakeholders.html', locals())

@ login_required(login_url='/login/')
def edit_stakeholders_untrust_po_report(request, stakeholders_id, task_id):
    heading = "Section 13: Edit of capacity building of different stakeholders"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    stakeholders_obj = Stakeholder.objects.get(id=stakeholders_id)
    if request.method == 'POST':
        data = request.POST
        user_name_id = data.get('user_name')
        master_trainers_male = data.get('master_trainers_male')
        master_trainers_female = data.get('master_trainers_female')
        master_trainers_total = data.get('master_trainers_total')
        nodal_teachers_male = data.get('nodal_teachers_male')
        nodal_teachers_female = data.get('nodal_teachers_female')
        nodal_teachers_total = data.get('nodal_teachers_total')
        principals_male = data.get('principals_male')
        principals_female = data.get('principals_female')
        principals_total = data.get('principals_total')
        district_level_officials_male = data.get('district_level_officials_male')
        district_level_officials_female = data.get('district_level_officials_female')
        district_level_officials_total = data.get('district_level_officials_total')
        peer_educator_male = data.get('peer_educator_male')
        peer_educator_female = data.get('peer_educator_female')
        peer_educator_total = data.get('peer_educator_total')
        state_level_officials_male = data.get('state_level_officials_male')
        state_level_officials_female = data.get('state_level_officials_female')
        state_level_officials_total = data.get('state_level_officials_total')
        icds_awws_male = data.get('icds_awws_male')
        icds_awws_female = data.get('icds_awws_female')
        icds_awws_total = data.get('icds_awws_total')
        icds_supervisors_male = data.get('icds_supervisors_male')
        icds_supervisors_female = data.get('icds_supervisors_female')
        icds_supervisors_total = data.get('icds_supervisors_total')
        icds_peer_educator_male = data.get('icds_peer_educator_male')
        icds_peer_educator_female = data.get('icds_peer_educator_female')
        icds_peer_educator_total = data.get('icds_peer_educator_total')
        icds_child_developement_project_officers_male = data.get('icds_child_developement_project_officers_male')
        icds_child_developement_project_officers_female = data.get('icds_child_developement_project_officers_female')
        icds_child_developement_project_officers_total = data.get('icds_child_developement_project_officers_total')
        icds_district_level_officials_male = data.get('icds_district_level_officials_male')
        icds_district_level_officials_female = data.get('icds_district_level_officials_female')
        icds_district_level_officials_total = data.get('icds_district_level_officials_total')
        icds_state_level_officials_male = data.get('icds_state_level_officials_male')
        icds_state_level_officials_female = data.get('icds_state_level_officials_female')
        icds_state_level_officials_total = data.get('icds_state_level_officials_total')
        health_ashas_male = data.get('health_ashas_male')
        health_ashas_female = data.get('health_ashas_female')
        health_ashas_total = data.get('health_ashas_total')
        health_anms_male = data.get('health_anms_male')
        health_anms_female = data.get('health_anms_female')
        health_anms_total = data.get('health_anms_total')
        health_bpm_bhm_pheos_male = data.get('health_bpm_bhm_pheos_male')
        health_bpm_bhm_pheos_female = data.get('health_bpm_bhm_pheos_female')
        health_bpm_bhm_pheos_total = data.get('health_bpm_bhm_pheos_total')
        health_medical_officers_male = data.get('health_medical_officers_male')
        health_medical_officers_female = data.get('health_medical_officers_female')
        health_medical_officers_total = data.get('health_medical_officers_total')
        health_district_level_officials_male = data.get('health_district_level_officials_male')
        health_district_level_officials_female = data.get('health_district_level_officials_female')
        health_district_level_officials_total = data.get('health_district_level_officials_total')
        health_state_level_officials_male = data.get('health_state_level_officials_male')
        health_state_level_officials_female = data.get('health_state_level_officials_female')
        health_state_level_officials_total = data.get('health_state_level_officials_total')
        health_rsk_male = data.get('health_rsk_male')
        health_rsk_female = data.get('health_rsk_female')
        health_rsk_total = data.get('health_rsk_total')
        health_peer_educator_male = data.get('health_peer_educator_male')
        health_peer_educator_female = data.get('health_peer_educator_female')
        health_peer_educator_total = data.get('health_peer_educator_total')
        panchayat_ward_members_male = data.get('panchayat_ward_members_male')
        panchayat_ward_members_female = data.get('panchayat_ward_members_female')
        panchayat_ward_members_total = data.get('panchayat_ward_members_total')
        panchayat_up_mukhiya_up_Pramukh_male = data.get('panchayat_up_mukhiya_up_Pramukh_male')
        panchayat_up_mukhiya_up_Pramukh_female = data.get('panchayat_up_mukhiya_up_Pramukh_female')
        panchayat_up_mukhiya_up_Pramukh_total = data.get('panchayat_up_mukhiya_up_Pramukh_total')
        panchayat_mukhiya_Pramukh_male = data.get('panchayat_mukhiya_Pramukh_male')
        panchayat_mukhiya_Pramukh_female = data.get('panchayat_mukhiya_Pramukh_female')
        panchayat_mukhiya_Pramukh_total = data.get('panchayat_mukhiya_Pramukh_total')
        panchayat_samiti_member_male = data.get('panchayat_samiti_member_male')
        panchayat_samiti_member_female = data.get('panchayat_samiti_member_female')
        panchayat_samiti_member_total = data.get('panchayat_samiti_member_total')
        panchayat_zila_parishad_member_male = data.get('panchayat_zila_parishad_member_male')
        panchayat_zila_parishad_member_female = data.get('panchayat_zila_parishad_member_female')
        panchayat_zila_parishad_member_total = data.get('panchayat_zila_parishad_member_total')
        panchayat_vc_zila_parishad_male = data.get('panchayat_vc_zila_parishad_male')
        panchayat_vc_zila_parishad_female = data.get('panchayat_vc_zila_parishad_female')
        panchayat_vc_zila_parishad_total = data.get('panchayat_vc_zila_parishad_total')
        panchayat_chairman_zila_parishad_male = data.get('panchayat_chairman_zila_parishad_male')
        panchayat_chairman_zila_parishad_female = data.get('panchayat_chairman_zila_parishad_female')
        panchayat_chairman_zila_parishad_total = data.get('panchayat_chairman_zila_parishad_total')
        panchayat_block_level_officials_male = data.get('panchayat_block_level_officials_male')
        panchayat_block_level_officials_female = data.get('panchayat_block_level_officials_female')
        panchayat_block_level_officials_total = data.get('panchayat_block_level_officials_total')
        panchayat_district_level_officials_male = data.get('panchayat_district_level_officials_male')
        panchayat_district_level_officials_female = data.get('panchayat_district_level_officials_female')
        panchayat_district_level_officials_total = data.get('panchayat_district_level_officials_total')
        panchayat_state_level_officials_male = data.get('panchayat_state_level_officials_male')
        panchayat_state_level_officials_female = data.get('panchayat_state_level_officials_female')
        panchayat_state_level_officials_total = data.get('panchayat_state_level_officials_total')
        media_interns_male = data.get('media_interns_male')
        media_interns_female = data.get('media_interns_female')
        media_interns_total = data.get('media_interns_total')
        media_journalists_male = data.get('media_journalists_male')
        media_journalists_female = data.get('media_journalists_female')
        media_journalists_total = data.get('media_journalists_total')
        media_editors_male = data.get('media_editors_male')
        media_editors_female = data.get('media_editors_female')
        media_editors_total = data.get('media_editors_total')
        others_block_cluster_field_corrdinators_male = data.get('others_block_cluster_field_corrdinators_male')
        others_block_cluster_field_corrdinators_female = data.get('others_block_cluster_field_corrdinators_female')
        others_block_cluster_field_corrdinators_total = data.get('others_block_cluster_field_corrdinators_total')
        others_ngo_staff_corrdinators_male = data.get('others_ngo_staff_corrdinators_male')
        others_ngo_staff_corrdinators_female = data.get('others_ngo_staff_corrdinators_female')
        others_ngo_staff_corrdinators_total = data.get('others_ngo_staff_corrdinators_total')
        others_male = data.get('others_male')
        others_female = data.get('others_female')
        others_total = data.get('others_total')
        total_male = data.get('total_male')
        total_female = data.get('total_female')
        total = data.get('total')
        task = Task.objects.get(id=task_id)

        if total and int(total) != 0:
            stakeholders_obj.user_name_id = request.user
            stakeholders_obj.master_trainers_male = master_trainers_male or None
            stakeholders_obj.master_trainers_female = master_trainers_female or None
            stakeholders_obj.master_trainers_total = master_trainers_total or None
            stakeholders_obj.nodal_teachers_male = nodal_teachers_male or None
            stakeholders_obj.nodal_teachers_female = nodal_teachers_female or None
            stakeholders_obj.nodal_teachers_total = nodal_teachers_total or None
            stakeholders_obj.principals_male = principals_male or None
            stakeholders_obj.principals_female = principals_female or None
            stakeholders_obj.principals_total = principals_total or None
            stakeholders_obj.district_level_officials_male = district_level_officials_male or None
            stakeholders_obj.district_level_officials_female = district_level_officials_female or None
            stakeholders_obj.district_level_officials_total = district_level_officials_total or None
            stakeholders_obj.peer_educator_male = peer_educator_male or None
            stakeholders_obj.peer_educator_female = peer_educator_female or None
            stakeholders_obj.peer_educator_total = peer_educator_total or None
            stakeholders_obj.state_level_officials_male = state_level_officials_male or None
            stakeholders_obj.state_level_officials_female = state_level_officials_female or None
            stakeholders_obj.state_level_officials_total = state_level_officials_total or None
            stakeholders_obj.icds_awws_male = icds_awws_male or None
            stakeholders_obj.icds_awws_female = icds_awws_female or None
            stakeholders_obj.icds_awws_total = icds_awws_total or None
            stakeholders_obj.icds_supervisors_male = icds_supervisors_male or None
            stakeholders_obj.icds_supervisors_female = icds_supervisors_female or None
            stakeholders_obj.icds_supervisors_total = icds_supervisors_total or None
            stakeholders_obj.icds_peer_educator_male = icds_peer_educator_male or None
            stakeholders_obj.icds_peer_educator_female = icds_peer_educator_female or None
            stakeholders_obj.icds_peer_educator_total = icds_peer_educator_total or None
            stakeholders_obj.icds_child_developement_project_officers_male = icds_child_developement_project_officers_male or None
            stakeholders_obj.icds_child_developement_project_officers_female = icds_child_developement_project_officers_female or None
            stakeholders_obj.icds_child_developement_project_officers_total = icds_child_developement_project_officers_total or None
            stakeholders_obj.icds_district_level_officials_male = icds_district_level_officials_male or None
            stakeholders_obj.icds_district_level_officials_female = icds_district_level_officials_female or None
            stakeholders_obj.icds_district_level_officials_total = icds_district_level_officials_total or None
            stakeholders_obj.icds_state_level_officials_male = icds_state_level_officials_male or None
            stakeholders_obj.icds_state_level_officials_female = icds_state_level_officials_female or None
            stakeholders_obj.icds_state_level_officials_total = icds_state_level_officials_total or None
            stakeholders_obj.health_ashas_male = health_ashas_male or None
            stakeholders_obj.health_ashas_female = health_ashas_female or None
            stakeholders_obj.health_ashas_total = health_ashas_total or None
            stakeholders_obj.health_anms_male = health_anms_male or None
            stakeholders_obj.health_anms_female = health_anms_female or None
            stakeholders_obj.health_anms_total = health_anms_total or None
            stakeholders_obj.health_bpm_bhm_pheos_male = health_bpm_bhm_pheos_male or None
            stakeholders_obj.health_bpm_bhm_pheos_female = health_bpm_bhm_pheos_female or None
            stakeholders_obj.health_bpm_bhm_pheos_total = health_bpm_bhm_pheos_total or None
            stakeholders_obj.health_medical_officers_male = health_medical_officers_male or None
            stakeholders_obj.health_medical_officers_female = health_medical_officers_female or None
            stakeholders_obj.health_medical_officers_total = health_medical_officers_total or None
            stakeholders_obj.health_district_level_officials_male = health_district_level_officials_male or None
            stakeholders_obj.health_district_level_officials_female = health_district_level_officials_female or None
            stakeholders_obj.health_district_level_officials_total = health_district_level_officials_total or None
            stakeholders_obj.health_state_level_officials_male = health_state_level_officials_male or None
            stakeholders_obj.health_state_level_officials_female = health_state_level_officials_female or None
            stakeholders_obj.health_state_level_officials_total = health_state_level_officials_total or None
            stakeholders_obj.health_rsk_male = health_rsk_male or None
            stakeholders_obj.health_rsk_female = health_rsk_female or None
            stakeholders_obj.health_rsk_total = health_rsk_total or None
            stakeholders_obj.health_peer_educator_male = health_peer_educator_male or None
            stakeholders_obj.health_peer_educator_female = health_peer_educator_female or None
            stakeholders_obj.health_peer_educator_total = health_peer_educator_total or None
            stakeholders_obj.panchayat_ward_members_male = panchayat_ward_members_male or None
            stakeholders_obj.panchayat_ward_members_female = panchayat_ward_members_female or None
            stakeholders_obj.panchayat_ward_members_total = panchayat_ward_members_total or None
            stakeholders_obj.panchayat_up_mukhiya_up_Pramukh_male = panchayat_up_mukhiya_up_Pramukh_male or None
            stakeholders_obj.panchayat_up_mukhiya_up_Pramukh_female = panchayat_up_mukhiya_up_Pramukh_female or None
            stakeholders_obj.panchayat_up_mukhiya_up_Pramukh_total = panchayat_up_mukhiya_up_Pramukh_total or None
            stakeholders_obj.panchayat_mukhiya_Pramukh_male = panchayat_mukhiya_Pramukh_male or None
            stakeholders_obj.panchayat_mukhiya_Pramukh_female = panchayat_mukhiya_Pramukh_female or None
            stakeholders_obj.panchayat_mukhiya_Pramukh_total = panchayat_mukhiya_Pramukh_total or None
            stakeholders_obj.panchayat_samiti_member_male = panchayat_samiti_member_male or None
            stakeholders_obj.panchayat_samiti_member_female = panchayat_samiti_member_female or None
            stakeholders_obj.panchayat_samiti_member_male = panchayat_samiti_member_total or None
            stakeholders_obj.panchayat_zila_parishad_member_male = panchayat_zila_parishad_member_male or None
            stakeholders_obj.panchayat_zila_parishad_member_female = panchayat_zila_parishad_member_female or None
            stakeholders_obj.panchayat_zila_parishad_member_total = panchayat_zila_parishad_member_total or None
            stakeholders_obj.panchayat_vc_zila_parishad_male = panchayat_vc_zila_parishad_male or None
            stakeholders_obj.panchayat_vc_zila_parishad_female = panchayat_vc_zila_parishad_female or None
            stakeholders_obj.panchayat_vc_zila_parishad_total = panchayat_vc_zila_parishad_total or None
            stakeholders_obj.panchayat_chairman_zila_parishad_male = panchayat_chairman_zila_parishad_male or None
            stakeholders_obj.panchayat_chairman_zila_parishad_female = panchayat_chairman_zila_parishad_female or None
            stakeholders_obj.panchayat_chairman_zila_parishad_total = panchayat_chairman_zila_parishad_total or None
            stakeholders_obj.panchayat_block_level_officials_male = panchayat_block_level_officials_male or None
            stakeholders_obj.panchayat_block_level_officials_female = panchayat_block_level_officials_female or None
            stakeholders_obj.panchayat_block_level_officials_total = panchayat_block_level_officials_total or None
            stakeholders_obj.panchayat_district_level_officials_male = panchayat_district_level_officials_male or None
            stakeholders_obj.panchayat_district_level_officials_female = panchayat_district_level_officials_female or None
            stakeholders_obj.panchayat_district_level_officials_total = panchayat_district_level_officials_total or None
            stakeholders_obj.panchayat_state_level_officials_male = panchayat_state_level_officials_male or None
            stakeholders_obj.panchayat_state_level_officials_female = panchayat_state_level_officials_female or None
            stakeholders_obj.panchayat_state_level_officials_total = panchayat_state_level_officials_total or None
            stakeholders_obj.media_interns_male = media_interns_male or None
            stakeholders_obj.media_interns_female = media_interns_female or None
            stakeholders_obj.media_interns_total = media_interns_total or None
            stakeholders_obj.media_journalists_male = media_journalists_male or None
            stakeholders_obj.media_journalists_female = media_journalists_female or None
            stakeholders_obj.media_journalists_total = media_journalists_total or None
            stakeholders_obj.media_editors_male = media_editors_male or None
            stakeholders_obj.media_editors_female = media_editors_female or None
            stakeholders_obj.media_editors_total = media_editors_total or None
            stakeholders_obj.others_block_cluster_field_corrdinators_male = others_block_cluster_field_corrdinators_male or None
            stakeholders_obj.others_block_cluster_field_corrdinators_female = others_block_cluster_field_corrdinators_female or None
            stakeholders_obj.others_block_cluster_field_corrdinators_total = others_block_cluster_field_corrdinators_total or None
            stakeholders_obj.others_ngo_staff_corrdinators_male = others_ngo_staff_corrdinators_male or None
            stakeholders_obj.others_ngo_staff_corrdinators_female = others_ngo_staff_corrdinators_female or None
            stakeholders_obj.others_ngo_staff_corrdinators_total = others_ngo_staff_corrdinators_total or None
            stakeholders_obj.others_male = others_male or None
            stakeholders_obj.others_female = others_female or None
            stakeholders_obj.others_total = others_total or None
            stakeholders_obj.total_male = total_male or None
            stakeholders_obj.total_female = total_female or None
            stakeholders_obj.total = total or None
            stakeholders_obj.task_id = task
            stakeholders_obj.site_id =  current_site
            stakeholders_obj.save()
            return redirect('/po-report/rnp/stakeholders-listing/'+str(task_id))
        else:
            error_message = 'Please, Enter the any one Category of participants for Achieved in this month'
    return render(request, 'po_report/untrust/stakeholders/edit_stakeholders.html', locals())


@ login_required(login_url='/login/')
def sessions_monitoring_listing_untrust_po_report(request, task_id):
    heading = "Section 14: Details of sessions monitoring and handholding support at block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    village_id =CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    sessions_monitoring = SessionMonitoring.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, sessions_monitoring)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/sessions_monitoring/sessions_monitoring_listing.html', locals())


@ login_required(login_url='/login/')
def add_sessions_monitoring_untrust_po_report(request, task_id):
    heading = "Section 14: Add of sessions monitoring and handholding support at block level"
    current_site = request.session.get('site_id')
    user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    user_report_spo = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    village_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__id')
    school_id = CC_School.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('school__id')
    sessions_monitoring = SessionMonitoring.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    village_obj = Village.objects.filter(status=1, id__in=village_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        name_of_visited = data.get('name_of_visited')
        selected_field_other = data.get('selected_field_other')
        
        
        if name_of_visited == '1':
            content_type_model='village'
            selected_object_id=data.get('selected_field_village')
        elif name_of_visited == '2':
            content_type_model='awc'
            selected_object_id=data.get('selected_field_awc')
        else:
            content_type_model='school'
            selected_object_id=data.get('selected_field_school')

        

        date = data.get('date')
        sessions = data.getlist('session_attended')
        session_attended = ", ".join(sessions)
        observation = data.get('observation')
        recommendation = data.get('recommendation')
        task = Task.objects.get(id=task_id)


        sessions_monitoring = SessionMonitoring.objects.create(name_of_visited=name_of_visited, session_attended=session_attended,
          date=date,
        observation=observation, recommendation=recommendation, task=task, site_id = current_site)
        
        if selected_object_id:
            content_type = ContentType.objects.get(model=content_type_model)
            sessions_monitoring.content_type=content_type
            sessions_monitoring.object_id=selected_object_id
        
        if name_of_visited in ['4','5']:
            sessions_monitoring.name_of_place_visited = selected_field_other

        sessions_monitoring.save()

        return redirect('/po-report/untrust/sessions-monitoring-listing/'+str(task_id))
    return render(request, 'po_report/untrust/sessions_monitoring/add_sessions_monitoring.html', locals())


@ login_required(login_url='/login/')
def edit_sessions_monitoring_untrust_po_report(request, sessions_id, task_id):
    heading = "Section 14: Edit of sessions monitoring and handholding support at block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    user_report_spo = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    village_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__id')
    school_id = CC_School.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('school__id')
    sessions_monitoring = SessionMonitoring.objects.get(id=sessions_id)
    session_choice = sessions_monitoring.session_attended.split(', ')
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    village_obj = Village.objects.filter(status=1, id__in=village_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        selected_field_other = data.get('selected_field_other')
        name_of_visited = data.get('name_of_visited')
        if name_of_visited == '1':
            content_type_model='village'
            selected_object_id=data.get('selected_field_village')
        elif name_of_visited == '2':
            content_type_model='awc'
            selected_object_id=data.get('selected_field_awc')
        else:
            content_type_model='school'
            selected_object_id=data.get('selected_field_school')

        content_type = ContentType.objects.get(model=content_type_model)
        date = data.get('date')
        sessions = data.getlist('session_attended')
        session_attended = ", ".join(sessions)
        observation = data.get('observation')
        recommendation = data.get('recommendation')
        task = Task.objects.get(id=task_id)

        sessions_monitoring.name_of_visited = name_of_visited

        if selected_object_id:
            content_type = ContentType.objects.get(model=content_type_model)
            sessions_monitoring.content_type=content_type
            sessions_monitoring.object_id=selected_object_id

        if name_of_visited in ['4','5']:
            sessions_monitoring.name_of_place_visited = selected_field_other

        sessions_monitoring.date = date
        sessions_monitoring.session_attended = session_attended
        sessions_monitoring.observation = observation
        sessions_monitoring.recommendation = recommendation
        sessions_monitoring.task_id = task
        sessions_monitoring.site_id =  current_site
        sessions_monitoring.save()
        return redirect('/po-report/untrust/sessions-monitoring-listing/'+str(task_id))
    return render(request, 'po_report/untrust/sessions_monitoring/edit_sessions_monitoring.html', locals())



@ login_required(login_url='/login/')
def facility_visits_listing_untrust_po_report(request, task_id):
    heading = "Section 15: Details of events & facility visits at block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    village_id =CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(status=1, user=request.user).values_list('awc__id')
    school_id = CC_School.objects.filter(status=1, user=request.user).values_list('school__id')
    facility_visits = Events.objects.filter(status=1, task__id = task_id)
    data = pagination_function(request, facility_visits)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/facility_visits/facility_visits_listing.html', locals())


@ login_required(login_url='/login/')
def add_facility_visits_untrust_po_report(request, task_id):
    heading = "Section 15: Add of events & facility visits at block level"
    current_site = request.session.get('site_id')
    user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    user_report_spo = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    village_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__id')
    school_id = CC_School.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('school__id')
    facility_visits = Events.objects.filter()
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    village_obj = Village.objects.filter(status=1, id__in=village_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        name_of_visited = data.get('name_of_visited')
        selected_field_other = data.get('selected_field_other')
        if name_of_visited == '1':
            content_type_model='village'
            selected_object_id=data.get('selected_field_village')
        elif name_of_visited == '2':
            content_type_model='awc'
            selected_object_id=data.get('selected_field_awc')
        else:
            content_type_model='school'
            selected_object_id=data.get('selected_field_school')

        date = data.get('date')
        purpose_visited = data.get('purpose_visited')
        observation = data.get('observation')
        recommendation = data.get('recommendation')
        task = Task.objects.get(id=task_id)

        
        facility_visits = Events.objects.create(name_of_visited=name_of_visited, purpose_visited=purpose_visited,
        date=date,
        observation=observation, recommendation=recommendation, task=task, site_id = current_site)
        
        if selected_object_id:
            content_type = ContentType.objects.get(model=content_type_model)
            facility_visits.content_type=content_type
            facility_visits.object_id=selected_object_id

        if name_of_visited in ['4','5','6','7','8','9','10','11']:
            facility_visits.name_of_place_visited = selected_field_other

        facility_visits.save()
        return redirect('/po-report/untrust/facility-visits-listing/'+str(task_id))
    return render(request, 'po_report/untrust/facility_visits/add_facility_visits.html', locals())


@ login_required(login_url='/login/')
def edit_facility_visits_untrust_po_report(request, facility_id, task_id):
    heading = "Section 15: Edit of events & facility visits at block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    user_report_po = MisReport.objects.filter(report_to = request.user).values_list('report_person__id', flat=True)
    user_report_spo = MisReport.objects.filter(report_to__id__in = user_report_po).values_list('report_person__id', flat=True)
    village_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__village__id')
    awc_id = CC_AWC_AH.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('awc__id')
    school_id = CC_School.objects.filter(Q(user__id__in=user_report_po) | Q(user__id__in=user_report_spo), status=1).values_list('school__id')
    facility_visits = Events.objects.get(id=facility_id)
    awc_obj = AWC.objects.filter(status=1, id__in=awc_id).order_by('name')
    village_obj = Village.objects.filter(status=1, id__in=village_id).order_by('name')
    school_obj = School.objects.filter(status=1, id__in=school_id).order_by('name')
    if request.method == 'POST':
        data = request.POST
        name_of_visited = data.get('name_of_visited')
        selected_field_other = data.get('selected_field_other')
        if name_of_visited == '1':
            content_type_model='village'
            selected_object_id=data.get('selected_field_village')
        elif name_of_visited == '2':
            content_type_model='awc'
            selected_object_id=data.get('selected_field_awc')
        else:
            content_type_model='school'
            selected_object_id=data.get('selected_field_school')

        date = data.get('date')
        purpose_visited = data.get('purpose_visited')
        observation = data.get('observation')
        recommendation = data.get('recommendation')
        task = Task.objects.get(id=task_id)

        facility_visits.name_of_visited = name_of_visited

        if selected_object_id:
            content_type = ContentType.objects.get(model=content_type_model)
            facility_visits.content_type = content_type
            facility_visits.object_id = selected_object_id
        
        if name_of_visited in ['4','5','6','7','8','9','10','11']:
            facility_visits.name_of_place_visited = selected_field_other

        facility_visits.date = date
        facility_visits.purpose_visited = purpose_visited
        facility_visits.observation = observation
        facility_visits.recommendation = recommendation
        facility_visits.task_id = task
        facility_visits.site_id =  current_site
        facility_visits.save()
        return redirect('/po-report/untrust/facility-visits-listing/'+str(task_id))
    return render(request, 'po_report/untrust/facility_visits/edit_facility_visits.html', locals())



@ login_required(login_url='/login/')
def followup_liaision_listing_untrust_po_report(request, task_id):
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    heading = "Section 17: Details of one to one (Follow up/ Liaison) meetings at district & Block Level"
    followup_liaision = FollowUP_LiaisionMeeting.objects.filter(user_name=request.user.id, task__id = task_id)
    data = pagination_function(request, followup_liaision)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/followup_liaision/followup_liaision_listing.html', locals())


@ login_required(login_url='/login/')
def add_followup_liaision_untrust_po_report(request, task_id):
    heading = "Section 17: Add of one to one (Follow up/ Liaison) meetings at district & Block Level"
    current_site = request.session.get('site_id')
    followup_liaision = FollowUP_LiaisionMeeting.objects.filter()
    meeting_obj = MasterLookUp.objects.filter(parent__slug = 'meeting-with-designation')
    if request.method == 'POST':
        data = request.POST
        date = data.get('date')
        district_block_level = data.get('district_block_level')
        meeting_id = data.get('meeting')
        meeting = MasterLookUp.objects.get(id = meeting_id)
        departments = data.get('departments')
        point_of_discussion = data.get('point_of_discussion')
        outcome = data.get('outcome')
        decision_taken = data.get('decision_taken')
        remarks = data.get('remarks')
        task = Task.objects.get(id=task_id)

        followup_liaision = FollowUP_LiaisionMeeting.objects.create(user_name=request.user, date=date,
        district_block_level=district_block_level, meeting_name=meeting, departments=departments, point_of_discussion=point_of_discussion,
        outcome=outcome, decision_taken=decision_taken, remarks=remarks, site_id = current_site, task=task)
        followup_liaision.save()
        return redirect('/po-report/untrust/followup-liaision-listing/'+str(task_id))
    return render(request, 'po_report/untrust/followup_liaision/add_followup_liaision.html', locals())


@ login_required(login_url='/login/')
def edit_followup_liaision_untrust_po_report(request, followup_liaision_id, task_id):
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    heading = "Section 17: Edit of one to one (Follow up/ Liaison) meetings at district & Block Level"
    current_site = request.session.get('site_id')
    followup_liaision = FollowUP_LiaisionMeeting.objects.get(id=followup_liaision_id)
    meeting_obj = MasterLookUp.objects.filter(parent__slug = 'meeting-with-designation')
    if request.method == 'POST':
        data = request.POST
        date = data.get('date')
        district_block_level = data.get('district_block_level')
        meeting_id = data.get('meeting')
        meeting = MasterLookUp.objects.get(id = meeting_id)
        departments = data.get('departments')
        point_of_discussion = data.get('point_of_discussion')
        outcome = data.get('outcome')
        decision_taken = data.get('decision_taken')
        remarks = data.get('remarks')
        task = Task.objects.get(id=task_id)


        followup_liaision.user_name = request.user
        followup_liaision.date = date
        followup_liaision.district_block_level = district_block_level
        followup_liaision.meeting_name = meeting
        followup_liaision.departments = departments
        followup_liaision.point_of_discussion = point_of_discussion
        followup_liaision.outcome = outcome
        followup_liaision.decision_taken = decision_taken
        followup_liaision.remarks = remarks
        followup_liaision.task_id = task
        followup_liaision.site_id =  current_site
        followup_liaision.save()
        return redirect('/po-report/untrust/followup-liaision-listing/'+str(task_id))
    return render(request, 'po_report/untrust/followup_liaision/edit_followup_liaision.html', locals())


@ login_required(login_url='/login/')
def participating_meeting_listing_untrust_po_report(request, task_id):
    heading = "Section 16: Details of participating in meetings at district and block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    participating_meeting = ParticipatingMeeting.objects.filter(user_name=request.user.id, task__id = task_id)
    data = pagination_function(request, participating_meeting)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/participating_meeting/participating_meeting_listing.html', locals())

@ login_required(login_url='/login/')
def add_participating_meeting_untrust_po_report(request, task_id):
    heading = "Section 16: Add of participating in meetings at district and block level"
    current_site = request.session.get('site_id')
    participating_meeting = ParticipatingMeeting.objects.filter()
    if request.method == 'POST':
        data = request.POST
        type_of_meeting = data.get('type_of_meeting')
        department = data.get('department')
        point_of_discussion = data.get('point_of_discussion')
        district_block_level = data.get('district_block_level')
        districit_level_officials = data.get('districit_level_officials')
        block_level = data.get('block_level')
        cluster_level = data.get('cluster_level')
        no_of_pri = data.get('no_of_pri')
        no_of_others = data.get('no_of_others')
        date = data.get('date')
        task = Task.objects.get(id=task_id)
        participating_meeting = ParticipatingMeeting.objects.create(user_name=request.user, type_of_meeting=type_of_meeting,
        department=department, point_of_discussion=point_of_discussion, districit_level_officials=districit_level_officials,
        block_level=block_level, cluster_level=cluster_level, no_of_pri=no_of_pri, no_of_others=no_of_others, 
        district_block_level=district_block_level, date=date, task=task, site_id = current_site,)
        participating_meeting.save()
        return redirect('/po-report/untrust/participating-meeting-listing/'+str(task_id))
    return render(request, 'po_report/untrust/participating_meeting/add_participating_meeting.html', locals())

@ login_required(login_url='/login/')
def edit_participating_meeting_untrust_po_report(request, participating_id, task_id):
    heading = "Section 16: Edit of participating in meetings at district and block level"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    participating_meeting = ParticipatingMeeting.objects.get(id=participating_id)
    if request.method == 'POST':
        data = request.POST
        type_of_meeting = data.get('type_of_meeting')
        department = data.get('department')
        district_block_level = data.get('district_block_level')
        point_of_discussion = data.get('point_of_discussion')
        districit_level_officials = data.get('districit_level_officials')
        block_level = data.get('block_level')
        cluster_level = data.get('cluster_level')
        no_of_pri = data.get('no_of_pri')
        no_of_others = data.get('no_of_others')
        date = data.get('date')
        task = Task.objects.get(id=task_id)

        participating_meeting.user_name = request.user
        participating_meeting.type_of_meeting = type_of_meeting
        participating_meeting.district_block_level = district_block_level
        participating_meeting.department = department
        participating_meeting.point_of_discussion = point_of_discussion
        participating_meeting.districit_level_officials = districit_level_officials
        participating_meeting.block_level = block_level
        participating_meeting.cluster_level = cluster_level
        participating_meeting.no_of_pri = no_of_pri
        participating_meeting.no_of_others = no_of_others
        participating_meeting.date = date
        participating_meeting.task_id = task
        participating_meeting.site_id =  current_site
        participating_meeting.save()
        return redirect('/po-report/untrust/participating-meeting-listing/'+str(task_id))
    return render(request, 'po_report/untrust/participating_meeting/edit_participating_meeting.html', locals())


@ login_required(login_url='/login/')
def faced_related_listing_untrust_po_report(request, task_id):
    heading = "Section 18: Details of faced related"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    faced_related = FacedRelatedOperation.objects.filter(user_name=request.user.id, task__id = task_id)
    data = pagination_function(request, faced_related)

    current_page = request.GET.get('page', 1)
    page_number_start = int(current_page) - 2 if int(current_page) > 2 else 1
    page_number_end = page_number_start + 5 if page_number_start + \
        5 < data.paginator.num_pages else data.paginator.num_pages+1
    display_page_range = range(page_number_start, page_number_end)
    return render(request, 'po_report/untrust/faced_related/faced_related_listing.html', locals())

@ login_required(login_url='/login/')
def add_faced_related_untrust_po_report(request, task_id):
    heading = "Section 18: Add of faced related"
    current_site = request.session.get('site_id')
    faced_related = FacedRelatedOperation.objects.filter()
    if request.method == 'POST':
        data = request.POST
        challenges = data.get('challenges')
        proposed_solution = data.get('proposed_solution')
        task = Task.objects.get(id=task_id)

        # if FacedRelatedOperation.objects.filter(Q(challenges__isnull=challenges) & Q(proposed_solution__isnull=proposed_solution)).exists():
        if challenges or proposed_solution:
            faced_related = FacedRelatedOperation.objects.create(user_name=request.user, challenges=challenges,
            proposed_solution=proposed_solution, task=task, site_id = current_site)
            faced_related.save()
        else:
            return redirect('/po-report/untrust/faced-related-listing/'+str(task_id))
        return redirect('/po-report/untrust/faced-related-listing/'+str(task_id))
    return render(request, 'po_report/untrust/faced_related/add_faced_related.html', locals())


@ login_required(login_url='/login/')
def edit_faced_related_untrust_po_report(request, faced_related_id, task_id):
    heading = "Section 18: Edit of faced related"
    task_obj = Task.objects.get(status=1, id=task_id)
    user = get_user(request)
    user_role = str(user.groups.last())
    current_site = request.session.get('site_id')
    faced_related = FacedRelatedOperation.objects.get(id=faced_related_id)
    if request.method == 'POST':
        data = request.POST
        challenges = data.get('challenges')
        proposed_solution = data.get('proposed_solution')
        task = Task.objects.get(id=task_id)
       
        if challenges or proposed_solution:
            faced_related.user_name = request.user
            faced_related.challenges = challenges
            faced_related.proposed_solution = proposed_solution
            faced_related.task_id = task
            faced_related.site_id =  current_site
            faced_related.save()
        else:
            return redirect('/po-report/fossil/faced-related-listing/'+str(task_id))
        return redirect('/po-report/untrust/faced-related-listing/'+str(task_id))
    return render(request, 'po_report/untrust/faced_related/edit_faced_related.html', locals())