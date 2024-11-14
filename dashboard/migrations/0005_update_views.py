# Generated by Django 3.2.6 on 2022-12-06 12:11

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0004_views_operation'),
    ]

    operations = [
            migrations.RunSQL('drop view if exists ahwd_info_view'),
            migrations.RunSQL('drop view if exists girls_ahwd_info_view'),
            migrations.RunSQL("""create or replace view girls_ahwd_info_view as 
                                    select ahwd.task_id, ahwd.site_id as ahwd_site, ahwd.date_of_ahwd as date_of_ahwd, mt.user_id, ams.id as school_id, awc.id as awc_id,
                                    ahwd.participated_10_14_years, ahwd.participated_15_19_years, ahwd.bmi_10_14_years, ahwd.bmi_15_19_years, ahwd.hb_10_14_years, ahwd.hb_15_19_years, ahwd.tt_10_14_years, ahwd.tt_15_19_years, ahwd.counselling_10_14_years, ahwd.counselling_15_19_years, ahwd.referral_10_14_years, ahwd.referral_15_19_years,ahwd.object_id as location_id,
                                    ams.village_id, vlg.name as village_name, vlg.grama_panchayat_id as gp_id, gp.name as gp_name, gp.block_id as block_id, blk.name as block_name, blk.district_id, dst.name as district_name, dst.state_id, st.name as state_name
                                    from mis_girlsahwd as ahwd
                                    inner join mis_task mt on mt.id = ahwd.task_id
                                    left outer join application_masters_school ams on ams.id = ahwd.object_id and ahwd.content_type_id = 16
                                    left outer join application_masters_awc awc on awc.id = ahwd.object_id and ahwd.content_type_id = 15
                                    left outer join application_masters_village vlg on (case when ams.village_id is not null then ams.village_id else awc.village_id end) = vlg.id 
                                    left outer join application_masters_gramapanchayat gp on gp.id = vlg.grama_panchayat_id 
                                    left outer join application_masters_block blk on blk.id = gp.block_id 
                                    left outer join application_masters_district dst on dst.id = blk.district_id 
                                    left outer join application_masters_state st on st.id = dst.state_id 
                                    where ahwd.status = 1"""),
            migrations.RunSQL('drop view if exists boys_ahwd_info_view'),
            migrations.RunSQL("""create or replace view boys_ahwd_info_view as 
                                    select ahwd.task_id, ahwd.site_id as ahwd_site, ahwd.date_of_ahwd as date_of_ahwd, mt.user_id, ams.id as school_id, awc.id as awc_id,
                                    ahwd.participated_10_14_years, ahwd.participated_15_19_years, ahwd.bmi_10_14_years, ahwd.bmi_15_19_years, ahwd.hb_10_14_years, ahwd.hb_15_19_years, 0 as tt_10_14_years, 0 as tt_15_19_years, ahwd.counselling_10_14_years, ahwd.counselling_15_19_years, ahwd.referral_10_14_years, ahwd.referral_15_19_years,ahwd.object_id as location_id,
                                    ams.village_id, vlg.name as village_name, vlg.grama_panchayat_id as gp_id, gp.name as gp_name, gp.block_id as block_id, blk.name as block_name, blk.district_id, dst.name as district_name, dst.state_id, st.name as state_name
                                    from mis_boysahwd as ahwd
                                    inner join mis_task mt on mt.id = ahwd.task_id
                                    left outer join application_masters_school ams on ams.id = ahwd.object_id and ahwd.content_type_id = 16
                                    left outer join application_masters_awc awc on awc.id = ahwd.object_id and ahwd.content_type_id = 15
                                    left outer join application_masters_village vlg on (case when ams.village_id is not null then ams.village_id else awc.village_id end) = vlg.id 
                                    left outer join application_masters_gramapanchayat gp on gp.id = vlg.grama_panchayat_id 
                                    left outer join application_masters_block blk on blk.id = gp.block_id 
                                    left outer join application_masters_district dst on dst.id = blk.district_id 
                                    left outer join application_masters_state st on st.id = dst.state_id 
                                    where ahwd.status = 1"""),
            migrations.RunSQL('drop view if exists adolescentre_enrolled_view'),
            migrations.RunSQL("""create or replace view adolescentre_enrolled_view as 
                                    select mae.task_id, mt.user_id, mae.site_id as enrolled_site,  mae.server_created_on::date as enrolled_date,
                                    mae.which_class_enrolled, mae.adolescent_name_id, adl.age_in_completed_years as adolescent_age_yrs, 
                                    adl.gender as adolescent_gender, adl.awc_id, awc.village_id as awc_village_id, vlg.grama_panchayat_id as awc_gp_id, gp.block_id as awc_block_id, blk.name as block_name, blk.district_id as awc_district_id,  dst.state_id as awc_state_id
                                    from mis_adolescentre_enrolled mae 
                                    inner join mis_task mt on mae.task_id = mt.id
                                    inner join application_masters_adolescent adl on adl.id = mae.adolescent_name_id
                                    inner join application_masters_awc awc on adl.awc_id = awc.id
                                    inner join application_masters_village vlg on awc.village_id = vlg.id 
                                    inner join application_masters_gramapanchayat gp on gp.id = vlg.grama_panchayat_id 
                                    inner join application_masters_block blk on blk.id = gp.block_id 
                                    inner join application_masters_district dst on dst.id = blk.district_id 
                                    inner join application_masters_state st on st.id = dst.state_id 
                                    where mae.status = 1 and adl.status = 1"""),                                    
        ]