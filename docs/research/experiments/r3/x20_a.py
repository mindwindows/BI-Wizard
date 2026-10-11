from r3lib import *
a=admin(); ids=json.load(open('base_ids.json'))['x20']
g=role_by_name(a,'Gamma'); c=role_by_name(a,'x20_author_copy'); s=role_by_name(a,'x20_author_schema_bi_data')
print('Gamma',len(g['permission_ids']),'copy',len(c['permission_ids']),'schema role',len(s['permission_ids']))
print('only in Gamma:',sorted(set(g['permission_ids'])-set(c['permission_ids'])),'only in copy:',sorted(set(c['permission_ids'])-set(g['permission_ids'])))
print('API result list for copy vs gamma identical:', sorted(g['permission_ids'])==sorted(c['permission_ids']))
print(psql("""SELECT r.name, count(*) FROM ab_permission_view_role pvr JOIN ab_role r ON r.id=pvr.role_id WHERE r.name IN ('Gamma','x20_author_copy','x20_author_schema_bi_data') GROUP BY r.name ORDER BY 1""", db='superset'))
print(psql("""SELECT count(*) FROM (SELECT permission_view_id FROM ab_permission_view_role WHERE role_id=(SELECT id FROM ab_role WHERE name='Gamma') EXCEPT SELECT permission_view_id FROM ab_permission_view_role WHERE role_id=(SELECT id FROM ab_role WHERE name='x20_author_copy')) x""", db='superset'), '(DB: Gamma minus copy)')
pvm=pvm_map(a); inv={v:k for k,v in pvm.items()}
names=sorted(f"{inv[i][0]} on {inv[i][1]}" for i in g['permission_ids'])
open('x20_gamma_perm_names.txt','w').write('\n'.join(names))
print('schema role perms:',[inv[i] for i in s['permission_ids']])
for k in ('can_set_embedded','can_get_embedded','can_delete_embedded'):
    print(k,'in Gamma?',pvm[(k,'Dashboard')] in g['permission_ids'])
for key in [('can_read','Dashboard'),('can_write','Dashboard'),('can_write','Chart'),('can_read','SQLLab'),('can_execute_sql_query','SQLLab'),('menu_access','SQL Lab'),('can_sql_json','Superset'),('can_csv','Superset'),('can_read','Dataset'),('can_write','Dataset'),('can_read','Database'),('can_write','Database'),('can_explore','Superset'),('can_samples','Datasource'),('can_export','Dashboard'),('can_read','Security')]:
    if key in pvm: print(key, 'Gamma' if pvm[key] in g['permission_ids'] else '-')
    else: print(key,'(pvm absent)')
