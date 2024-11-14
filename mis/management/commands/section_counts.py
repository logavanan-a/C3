from django.core.management.base import BaseCommand
from dateutil.relativedelta import relativedelta
from application_masters.models import *
from django.contrib.auth.models import User
from django.contrib.auth.models import Group

from mis.models import *
import datetime
import time
from datetime import timedelta
from django.utils import timezone
from django.utils.timezone import localtime
    



def get_section_count():
    today_date = datetime.date.today()
    print(today_date, 'today_date')
    current_week_first_day = today_date - datetime.timedelta(days=today_date.weekday())
    print(current_week_first_day, 'current_week_first_day')
    current_month_first_day = datetime.date.today().replace(day=1)
    print(current_month_first_day, 'current_month_first_day')

    #AH Section
    today_count_ah_section = AHSession.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_ah_section = AHSession.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_ah_section = AHSession.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_ah_section = AHSession.objects.filter(status=1).count()
    last_created_on_ah_section = AHSession.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_ah_section_datetime = (localtime(last_created_on_ah_section).strftime("%Y-%m-%d %H:%M:%S"))

    #DL Section
    today_count_dl_section = DLSession.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_dl_section = DLSession.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_dl_section = DLSession.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_dl_section = DLSession.objects.filter(status=1).count()
    last_created_on_dl_section = DLSession.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_dl_section_datetime = (localtime(last_created_on_dl_section).strftime("%Y-%m-%d %H:%M:%S"))

    #Girls vocational training
    today_count_girls_vocational_training = AdolescentVocationalTraining.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_girls_vocational_training = AdolescentVocationalTraining.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_girls_vocational_training = AdolescentVocationalTraining.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_girls_vocational_training = AdolescentVocationalTraining.objects.filter(status=1).count()
    last_created_on_girls_vocational_training = AdolescentVocationalTraining.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_girls_vocational_training_datetime = (localtime(last_created_on_girls_vocational_training).strftime("%Y-%m-%d %H:%M:%S"))

    #Parents vocational training
    today_count_parents_vocational_training = ParentVocationalTraining.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_parents_vocational_training = ParentVocationalTraining.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_parents_vocational_training = ParentVocationalTraining.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_parents_vocational_training = ParentVocationalTraining.objects.filter(status=1).count()
    last_created_on_parents_vocational_training = AdolescentVocationalTraining.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_parents_vocational_training_datetime = (localtime(last_created_on_parents_vocational_training).strftime("%Y-%m-%d %H:%M:%S"))

    #Girls(AHWD)
    today_count_girls_ahwd = GirlsAHWD.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_girls_ahwd = GirlsAHWD.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_girls_ahwd = GirlsAHWD.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_girls_ahwd = GirlsAHWD.objects.filter(status=1).count()
    last_created_on_girls_ahwd = AdolescentVocationalTraining.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_girls_ahwd_datetime = (localtime(last_created_on_girls_ahwd).strftime("%Y-%m-%d %H:%M:%S"))

    #Boys(AHWD)
    today_count_boys_ahwd = BoysAHWD.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_boys_ahwd = BoysAHWD.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_boys_ahwd = BoysAHWD.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_boys_ahwd = BoysAHWD.objects.filter(status=1).count()
    last_created_on_boys_ahwd = AdolescentVocationalTraining.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_boys_ahwd_datetime = (localtime(last_created_on_boys_ahwd).strftime("%Y-%m-%d %H:%M:%S"))

    #Adolescents Referred
    today_count_adolescents_referred = AdolescentsReferred.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_adolescents_referred = AdolescentsReferred.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_adolescents_referred = AdolescentsReferred.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_adolescents_referred = AdolescentsReferred.objects.filter(status=1).count()
    last_created_on_adolescents_referred = AdolescentVocationalTraining.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_adolescents_referred_datetime = (localtime(last_created_on_adolescents_referred).strftime("%Y-%m-%d %H:%M:%S"))
    
    #Adolescent Friendly Club
    today_count_adolescent_friendly_club = AdolescentFriendlyClub.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_adolescent_friendly_club = AdolescentFriendlyClub.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_adolescent_friendly_club = AdolescentFriendlyClub.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_adolescent_friendly_club = AdolescentFriendlyClub.objects.filter(status=1).count()
    last_created_on_adolescent_friendly_club = AdolescentVocationalTraining.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_adolescent_friendly_club_datetime = (localtime(last_created_on_adolescent_friendly_club).strftime("%Y-%m-%d %H:%M:%S"))

    #Adolescent Bal Sansad Meeting
    today_count_adolescent_balsansad_meeting = BalSansadMeeting.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_adolescent_balsansad_meeting = BalSansadMeeting.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_adolescent_balsansad_meeting = BalSansadMeeting.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_adolescent_balsansad_meeting = BalSansadMeeting.objects.filter(status=1).count()
    last_created_on_adolescent_balsansad_meeting = BalSansadMeeting.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_adolescent_balsansad_meeting_datetime = (localtime(last_created_on_adolescent_balsansad_meeting).strftime("%Y-%m-%d %H:%M:%S"))

    #Community Engagement Activities
    today_count_community_engagement_activities = CommunityEngagementActivities.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_community_engagement_activities = CommunityEngagementActivities.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_community_engagement_activities = CommunityEngagementActivities.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_community_engagement_activities = CommunityEngagementActivities.objects.filter(status=1).count()
    last_created_on_community_engagement_activities = CommunityEngagementActivities.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_community_engagement_activities_datetime = (localtime(last_created_on_community_engagement_activities).strftime("%Y-%m-%d %H:%M:%S"))

    #Champions
    today_count_champions = Champions.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_champions = Champions.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_champions = Champions.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_champions = Champions.objects.filter(status=1).count()
    last_created_on_champions = Champions.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_champions_datetime = (localtime(last_created_on_champions).strftime("%Y-%m-%d %H:%M:%S"))

    #Adolescent Re_enrolled
    today_count_adolescent_reenrolled = AdolescentRe_enrolled.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_adolescent_reenrolled = AdolescentRe_enrolled.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_adolescent_reenrolled = AdolescentRe_enrolled.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_adolescent_reenrolled = AdolescentRe_enrolled.objects.filter(status=1).count()
    last_created_on_adolescent_reenrolled = AdolescentRe_enrolled.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_adolescent_reenrolled_datetime = (localtime(last_created_on_adolescent_reenrolled).strftime("%Y-%m-%d %H:%M:%S"))

    #VLCPC Metting
    today_count_vlcpc_metting = VLCPCMetting.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_vlcpc_metting = VLCPCMetting.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_vlcpc_metting = VLCPCMetting.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_vlcpc_metting = VLCPCMetting.objects.filter(status=1).count()
    last_created_on_vlcpc_metting = VLCPCMetting.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_vlcpc_metting_datetime = (localtime(last_created_on_vlcpc_metting).strftime("%Y-%m-%d %H:%M:%S"))

    #DCPU/BCPU engagement at community and institutional level
    today_count_dcpu_bcpu = DCPU_BCPU.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_dcpu_bcpu = DCPU_BCPU.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_dcpu_bcpu = DCPU_BCPU.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_dcpu_bcpu = DCPU_BCPU.objects.filter(status=1).count()
    last_created_on_dcpu_bcpu = DCPU_BCPU.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_dcpu_bcpu_datetime = (localtime(last_created_on_dcpu_bcpu).strftime("%Y-%m-%d %H:%M:%S"))

    #Educational enrichment support provided
    today_count_educatinal_enrichment_support_provided = EducatinalEnrichmentSupportProvided.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_educatinal_enrichment_support_provided = EducatinalEnrichmentSupportProvided.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_educatinal_enrichment_support_provided = EducatinalEnrichmentSupportProvided.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_educatinal_enrichment_support_provided = EducatinalEnrichmentSupportProvided.objects.filter(status=1).count()
    last_created_on_educatinal_enrichment_support_provided = EducatinalEnrichmentSupportProvided.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_educatinal_enrichment_support_provided_datetime = (localtime(last_created_on_educatinal_enrichment_support_provided).strftime("%Y-%m-%d %H:%M:%S"))

    #Stakeholder
    today_count_stakeholder = Stakeholder.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_stakeholder = Stakeholder.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_stakeholder = Stakeholder.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_stakeholder = Stakeholder.objects.filter(status=1).count()
    last_created_on_stakeholder = Stakeholder.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_stakeholder_datetime = (localtime(last_created_on_stakeholder).strftime("%Y-%m-%d %H:%M:%S"))

    #Session Monitoring
    today_count_session_monitoring = SessionMonitoring.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_session_monitoring = SessionMonitoring.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_session_monitoring = SessionMonitoring.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_session_monitoring = SessionMonitoring.objects.filter(status=1).count()
    last_created_on_session_monitoring = SessionMonitoring.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_session_monitoring_datetime = (localtime(last_created_on_session_monitoring).strftime("%Y-%m-%d %H:%M:%S"))

    #Events & facility visits at block level
    today_count_events_and_facility_visits = Events.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_events_and_facility_visits = Events.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_events_and_facility_visits = Events.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_events_and_facility_visits = Events.objects.filter(status=1).count()
    last_created_on_events_and_facility_visits = Events.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_events_and_facility_visits_datetime = (localtime(last_created_on_events_and_facility_visits).strftime("%Y-%m-%d %H:%M:%S"))

    #Participating Meeting
    today_count_participating_meeting = ParticipatingMeeting.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_participating_meeting = ParticipatingMeeting.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_participating_meeting = ParticipatingMeeting.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_participating_meeting = ParticipatingMeeting.objects.filter(status=1).count()
    last_created_on_participating_meeting = ParticipatingMeeting.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_participating_meeting_datetime = (localtime(last_created_on_participating_meeting).strftime("%Y-%m-%d %H:%M:%S"))

    #Follow UP Liaision Meeting
    today_count_follow_up_liaision_meeting = FollowUP_LiaisionMeeting.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_follow_up_liaision_meeting = FollowUP_LiaisionMeeting.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_follow_up_liaision_meeting = FollowUP_LiaisionMeeting.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_follow_up_liaision_meeting = FollowUP_LiaisionMeeting.objects.filter(status=1).count()
    last_created_on_follow_up_liaision_meeting = FollowUP_LiaisionMeeting.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_follow_up_liaision_meeting_datetime = (localtime(last_created_on_follow_up_liaision_meeting).strftime("%Y-%m-%d %H:%M:%S"))

    #Follow UP Liaision Meeting
    today_count_faced_related_operation = FacedRelatedOperation.objects.filter(status=1, server_created_on__date=today_date).count()
    current_week_count_faced_related_operation = FacedRelatedOperation.objects.filter(status=1, server_created_on__date__range=[current_week_first_day, today_date]).count()
    current_month_count_faced_related_operation = FacedRelatedOperation.objects.filter(status=1, server_created_on__date__range=[current_month_first_day, today_date]).count()
    over_all_count_faced_related_operation = FacedRelatedOperation.objects.filter(status=1).count()
    last_created_on_faced_related_operation = FacedRelatedOperation.objects.filter(status=1).values_list('server_created_on', flat=True).last()
    last_created_on_faced_related_operation_datetime = (localtime(last_created_on_faced_related_operation).strftime("%Y-%m-%d %H:%M:%S"))


    from tabulate import tabulate
    print('model list-----------------')
    data=[[1, 'Health & nutrition sessions', today_count_ah_section, current_week_count_ah_section, current_month_count_ah_section, over_all_count_ah_section, last_created_on_ah_section_datetime],
    [2, 'Digital literacy sessions', today_count_dl_section, current_week_count_dl_section, current_month_count_dl_section, over_all_count_dl_section, last_created_on_dl_section_datetime],
    [3, 'Adolescent girls linked with vocational training & placement', today_count_girls_vocational_training, current_week_count_girls_vocational_training, current_month_count_girls_vocational_training, over_all_count_girls_vocational_training, last_created_on_girls_vocational_training_datetime],
    [4, 'Parents of at risk girls linked with vocational training & placement', today_count_parents_vocational_training, current_week_count_parents_vocational_training, current_month_count_parents_vocational_training, over_all_count_parents_vocational_training, last_created_on_parents_vocational_training_datetime],
    [5, 'Participation of adolescent girls in Adolescent Health Wellness Day (AHWD)', today_count_girls_ahwd, current_week_count_girls_ahwd, current_month_count_girls_ahwd, over_all_count_girls_ahwd, last_created_on_girls_ahwd_datetime],
    [6, 'Participation of adolescent boys in Adolescent Health Wellness Day (AHWD)', today_count_boys_ahwd, current_week_count_boys_ahwd, current_month_count_boys_ahwd, over_all_count_boys_ahwd, last_created_on_boys_ahwd_datetime],
    [7, 'Adolescents referred', today_count_adolescents_referred, current_week_count_adolescents_referred, current_month_count_adolescents_referred, over_all_count_adolescents_referred, last_created_on_adolescents_referred_datetime],
    [8, 'Adolescent Friendly Club (AFC)', today_count_adolescent_friendly_club, current_week_count_adolescent_friendly_club, current_month_count_adolescent_friendly_club, over_all_count_adolescent_friendly_club, last_created_on_adolescent_friendly_club_datetime],
    [9, 'Bal Sansad meetings conducted', today_count_adolescent_balsansad_meeting, current_week_count_adolescent_balsansad_meeting, current_month_count_adolescent_balsansad_meeting, over_all_count_adolescent_balsansad_meeting, last_created_on_adolescent_balsansad_meeting_datetime],
    [10, 'Community engagement activities', today_count_community_engagement_activities, current_week_count_community_engagement_activities, current_month_count_community_engagement_activities, over_all_count_community_engagement_activities, last_created_on_community_engagement_activities_datetime],
    [11, 'Exposure visits of adolescent champions', today_count_champions, current_week_count_champions, current_month_count_champions, over_all_count_champions, last_created_on_champions_datetime],
    [12, 'Adolescent re-enrolled in schools', today_count_adolescent_reenrolled, current_week_count_adolescent_reenrolled, current_month_count_adolescent_reenrolled, over_all_count_adolescent_reenrolled, last_created_on_adolescent_reenrolled_datetime],
    [13, 'VLCPC meetings', today_count_vlcpc_metting, current_week_count_vlcpc_metting, current_month_count_vlcpc_metting, over_all_count_vlcpc_metting, last_created_on_vlcpc_metting_datetime],
    [14, 'DCPU/BCPU engagement at community and institutional level', today_count_dcpu_bcpu, current_week_count_dcpu_bcpu, current_month_count_dcpu_bcpu, over_all_count_dcpu_bcpu, last_created_on_dcpu_bcpu_datetime],
    [15, 'Educational enrichment support provided', today_count_educatinal_enrichment_support_provided, current_week_count_educatinal_enrichment_support_provided, current_month_count_educatinal_enrichment_support_provided, over_all_count_educatinal_enrichment_support_provided, last_created_on_educatinal_enrichment_support_provided_datetime],
    [16, 'Capacity building of different stakeholders', today_count_stakeholder, current_week_count_stakeholder, current_month_count_stakeholder, over_all_count_stakeholder, last_created_on_stakeholder_datetime],
    [17, 'Sessions monitoring and handholding support at block level', today_count_session_monitoring, current_week_count_session_monitoring, current_month_count_session_monitoring, over_all_count_session_monitoring, last_created_on_session_monitoring_datetime],
    [18, 'Events & facility visits at block level', today_count_events_and_facility_visits, current_week_count_events_and_facility_visits, current_month_count_events_and_facility_visits, over_all_count_events_and_facility_visits, last_created_on_events_and_facility_visits_datetime],
    [19, 'Participating in meetings at district and block level', today_count_participating_meeting, current_week_count_participating_meeting, current_month_count_participating_meeting, over_all_count_participating_meeting, last_created_on_participating_meeting_datetime],
    [20, 'One to one (Follow up/ Liaison) meetings at district & Block Level', today_count_follow_up_liaision_meeting, current_week_count_follow_up_liaision_meeting, current_month_count_follow_up_liaision_meeting, over_all_count_follow_up_liaision_meeting, last_created_on_follow_up_liaision_meeting_datetime],
    [21, 'Faced related to the operation of the program', today_count_faced_related_operation, current_week_count_faced_related_operation, current_month_count_faced_related_operation, over_all_count_faced_related_operation, last_created_on_faced_related_operation_datetime],
    ]
    # for i in data:
    #     print(i[0])
    print(tabulate(data, headers=["ID", "Model List", "Today", "Current Week", "Current Month", "Over all", "Last create on"]))
   
    task='kjvkjdsvkjbdkjvb'
    return task

    
class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        get_section_count()