import os
file_path = r'C:\Users\User\Documents\GitHub\Graceinn\gracedayinnsystem\apps\frontend\templates\portals\guests.html'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    '<th class="text-center text-uppercase text-secondary text-xxs font-weight-bolder opacity-7">Phone</th>',
    '<th class="text-center text-uppercase text-secondary text-xxs font-weight-bolder opacity-7">Phone</th>\n                                <th class="text-center text-uppercase text-secondary text-xxs font-weight-bolder opacity-7">ID Doc</th>'
)

content = content.replace(
    '<td class="align-middle text-center"><span class="text-secondary text-xs font-weight-bold">{{ guest.phone|default:\'-\' }}</span></td>',
    '<td class="align-middle text-center"><span class="text-secondary text-xs font-weight-bold">{{ guest.phone|default:\'-\' }}</span></td>\n                                    <td class="align-middle text-center">{% if guest.id_document %}<a href="{{ guest.id_document.url }}" target="_blank" class="badge bg-gradient-info text-white">View ID</a>{% else %}<span class="text-secondary text-xs">None</span>{% endif %}</td>'
)

content = content.replace('<td colspan="5"', '<td colspan="6"')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
