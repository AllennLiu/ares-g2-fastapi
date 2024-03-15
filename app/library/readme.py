#!/usr/bin/python3
# -*- coding: utf-8 -*-

from library.config import GLOBAL_ROOT_PATH
from schemas import MissionInfo, LogType
from gitlabs import Project, getProject, getReadme

from markdown import markdown
from contextlib import suppress
from typing import Any, Dict, List, Type, Union
from re import sub, search, compile, escape, findall

MARKDOWN_EXTENSTIONS = [ 'nl2br', 'tables', 'codehilite', 'fenced_code', 'sane_lists' ]
MARKDOWN_CODE_LANGS = [ 'sh', 'bash', 'ini', 'yml', 'yaml', 'toml', 'python', 'html', 'js', 'json', 'javascript' ]

def markdown_h1_url(content: str, download: str, messages: List[str]) -> str:
    lines = content.splitlines()
    header = [ e for e in lines if '<h2>Suitable Project</h2>' in e ]
    header = header.pop()
    msg_lines = '\n'.join([ f'<li>{e}</li>' for e in messages if e.strip() ])
    return content.replace(
        header,
        '<h2>Change List</h2>\n' +
        f'<ol>\n{msg_lines}</ol>\n' +
        '<h2>Download</h2>\n\n' +
        f'脚本下载：<a href="{download}">下载连结</a>\n' +
        f'\n{header}'
    )

def markdown_remove(content: str, items: List[str]) -> str:
    lines = content.splitlines()
    for item in items:
        content = '\n'.join( e for e in lines if item not in e )
    return content

def markdown_remove_duplicate(content: str, item: str) -> str:
    return content.replace(f'{item}\n{item}', item)

def markdown_code(content: str) -> str:
    tag_pre = '<pre style="padding: 0px 10px 10px 10px; background-color: #272822;">'
    tag_code = '<code class="language-%s" style="padding: 10px; color: #f8f8f2;">'
    for e in MARKDOWN_CODE_LANGS:
        content = content.replace(f'<code>{e}', f'{tag_pre}{tag_code % e}  ')
    return content.replace('</code>', '</code></pre>')

def markdown_checkbox(content: str = '', gitlab: bool = False) -> str:
    checked   = '<br>✔'
    uncheck   = '<br>❌'
    checked_r = r'<li>\s{0,}\-{0,}\s{0,}\[[xX]]\s{0,}'
    uncheck_r = r'<li>\s{0,}\-{0,}\s{0,}\[\s{0,}]\s{0,}'
    input_c_r = r'<ul>\n{0,}<br><input\s+type="checkbox"'
    suitable_header = '<h2>Suitable Project</h2>\n'
    status_header = '\n<hr />\n<h2>Status</h2>'
    if gitlab:
        checked = '<br><input type="checkbox" checked="on">'
        uncheck = '<br><input type="checkbox">'
    content = sub(checked_r, checked, content)
    content = sub(uncheck_r, uncheck, content)
    content = sub(input_c_r, '<ul><input type="checkbox"', content)
    content = content.replace(f'{suitable_header}<ul>', suitable_header)
    content = content.replace(f'</li>\n</ul>{status_header}', f'\n<br><br>{status_header}')
    if not gitlab:
        content = sub(suitable_header + r'(\n|<br>)+', suitable_header, content)
    return content

def markdown_highlight(content: str) -> str:
    styles = """; color: #1f1f1f; background-color: #f0f0f0;
    border-radius: 4px; font-size: 90%; white-space: pre-wrap;
    overflow-wrap: break-word; word-break: keep-all;"""
    return content.replace('<code>', f'<code style="padding: 3px 5px{styles}">')

def markdown_wordframe(content: str) -> str:
    styles = 'border-radius: 2px; padding: 2px 4px; background-color: #'
    return (
        content.replace('{+ ', f'<span style="{styles}c7f0d2;">')
        .replace('{- ', f'<span style="{styles}fac5cd;">')
        .replace(' +}', '</span>')
        .replace(' -}', '</span>')
    )

def markdown_table(content: str = '') -> str:
    styles = 'border: 1px solid #ddd; border-bottom: 1.5px solid #ddd;'
    return content.replace('<td ', f'<td style="padding: 8px; {styles}" ')

def readme_decorator(readme: str = '') -> str:
    readme = markdown(readme, extensions=MARKDOWN_EXTENSTIONS)
    readme = markdown_code(content=readme)
    readme = markdown_checkbox(content=readme, gitlab=True)
    readme = markdown_table(content=readme)
    readme = markdown_highlight(content=readme)
    readme = markdown_wordframe(content=readme)
    return readme

def readme_release(readme: str, download: str, messages: List[str]) -> str:
    content = markdown(readme, extensions=MARKDOWN_EXTENSTIONS)
    content = markdown_h1_url(content, download, messages)
    content = markdown_remove(content, [ '<h2>Status</h2>', '/pipeline.svg' ])
    content = markdown_code(content)
    content = markdown_checkbox(content)
    content = markdown_highlight(content)
    content = markdown_wordframe(content)
    return markdown_remove_duplicate(content, '<hr />')

def search_readme(content: str = '', regexp: str = '', idx: int = 1) -> str:
    lines = [ e for e in content.splitlines() if e.strip() ]
    if not (resp := [ lines[i+idx] for i, e in enumerate(lines) if search(regexp, e) ]):
        return ''
    return str(resp) if len(resp) > 1 else resp[0]

def get_script_name_func(name: str = '', excludes: List[str] = [ 'script' ]) -> str:
    middles = name.split('-')[1:-1]
    exclude = ''.join(middles).lower() not in excludes
    return '/'.join(middles) if middles and exclude else 'Common'

def get_ver_by_readme(name: str = '', id: int = 0,
    by_project: Type[Project] = None, ref: str = 'master',
    readme: Union[str, None] = '') -> str:
    try:
        project = by_project or getProject(id, name)
        readme = readme or getReadme(project, ref)
        content = search_readme(readme, '## Version')
        return sub(r'[^(\d+\.){2}\d+]', '', content)
    except Exception:
        return '0.0.0'

def get_developer_by_readme(content: str = '') -> str:
    lines = content.splitlines()
    try:
        return ''.join([
            [ l for l in lines[i+1:i+3] if search(r'^\s+\-', l) ][0].split(' - ')[-1].strip()
            for i, e in enumerate(lines) if 'Developer' in e
        ])
    except Exception:
        return ''

def get_testers_by_readme(content: str = '') -> List[str]:
    lines = content.splitlines()
    regexp = r'by\s+.*.\s(on|as|at)'
    key = 'script has been validated by'
    try:
        return [
            search(regexp, e).group().split()[1].split()[-1]
            for e in lines if key in e.lower() and search(regexp, e)
        ]
    except Exception:
        return []

def get_readme_splits(
    content: str = '', pattern: str = '', splitext: str = '\n---\n') -> List[str]:
    return [ e for e in content.split(splitext) if pattern in e ]

def get_readme_content(readme: str = '', regexp: str = '') -> str:
    if not (lines := get_readme_splits(readme, regexp)):
        return ''
    return sub(r'\n{0}\n\n|\n$'.format(escape(regexp)), '', lines[0])

def get_readme_reports(readme: str = '', resp: List[LogType] = []) -> List[LogType]:
    lines = get_readme_splits(readme, '## Reports')
    if not lines:
        return []
    content = sub(r'\n+', '\n', lines[0]).splitlines()
    for e in content:
        if search(r'Log\sFile\s`\w+', e):
            with suppress(Exception):
                fn = findall(r'File\s`\S+`', e)[0].split()[-1].strip('`')
                desc = e.split('`**: ')[-1].strip()
                resp.append(LogType(filename=fn, description=desc).dict())
    return resp

def get_readme_coverage(readme: str = '') -> Dict[str, Any]:
    lines = get_readme_splits(readme, '## Coverage')
    if not lines:
        return {}
    content = sub(r'\n+', '\n', lines[0]).splitlines()
    return {
        b[0]: { "platform": b[2], "project": b[1] }
        for b in [
            [ l.strip() for l in a.split('|') ][1:]
            for a in [ e for e in content if search(r'^\| .*', e) ][1:]
        ]
    }

def get_readme_associates(readme: str = '') -> Dict[str, Any]:
    lines = get_readme_splits(readme, '## Associates')
    if not lines:
        return {}
    content = sub(r'\n+', '\n', lines[0]).splitlines()
    return {
        "owner": [
            content[i+1] for i, e in enumerate(content) if 'PIC' in e
        ][0].split(' - ')[-1].strip(),
        "lte_name": [
            content[i+1] for i, e in enumerate(content) if 'Test Leader' in e
        ][0].split(' - ')[-1].strip(),
        "developer": [
            content[i+1] for i, e in enumerate(content) if 'Developer' in e
        ][0].split(' - ')[-1].strip(),
        "te_name": ';'.join([
            l.strip()
            for l in sub(
                r'\*\*Developer.*',
                '',
                ''.join([
                    content[i+1:] for i, e in enumerate(content)
                    if 'Tester' in e
                ][0])).split(' - ')
            if l.strip()
        ])
    }

def get_readme_validation(readme: str = '') -> Dict[str, Any]:
    lines = get_readme_splits(readme, '## Validation')
    if not lines:
        return {}
    content = sub(r'\n+', '\n', lines[0]).splitlines()
    return {
        b[0]: {
            "name"    : b[0],
            "customer": "",
            "project" : b[1],
            "platform": "",
            "reports" : (
                findall(r'\(.*.\)', b[4])[0].replace('(', '').replace(')', '')
                if b[4] and b[4] != 'None' else ""
            ),
            "validation": "False",
            "result": (
                b[3].replace('{+', '').replace('+}', '').replace('{-', '').replace('-}', '')
                    .strip().lower()
            ),
            "datetime": b[2]
        }
        for b in [
            [ l.strip() for l in a.split('|') ][1:]
            for a in [ e for e in content if search(r'^\| .*', e) ][1:]
        ]
    }

def get_readme_testing_methodology(readme: str = '') -> Dict[str, Any]:
    lines = get_readme_splits(readme, '## Testing Methodology')
    if not lines:
        return {}
    content = sub(r'\n+', '\n', lines[0]).splitlines()
    return {
        findall(r'\[.*.\]', b[1])[0].replace('[', '').replace(']', ''): {
            "bkm_name": b[0],
            "bkm_id"  : findall(r'\[.*.\]', b[1])[0].replace('[', '').replace(']', ''),
            "bkm_link": findall(r'\(.*.\)', b[1])[0].replace('(', '').replace(')', ''),
            "bkm_objective": b[2],
            "bkm_version"  : b[3]
        }
        for b in [
            [ l.strip() for l in a.split('|') if l.strip() ]
            for a in [ e for e in content if search(r'^\| .*', e) ][1:]
        ]
    }

def get_readme_estimate(readme: str = '', estimate: str = '0') -> str:
    readme_estimate = search_readme(readme, '## Estimate')
    match = search(r'\d+(\.\d+){0,}', readme_estimate)
    return match.group() if match else estimate

def readme_update_content(readme: str, regexp: str, value: str) -> str:
    return '\n---\n'.join([
        f'\n{regexp}\n\n{value}\n'.replace('\r', '')
        if regexp in e else e
        for e in readme.split('\n---\n')
    ])

def readme_update_version(readme: str, version: str) -> str:
    return sub(r'`Rev:\s(\d+\.){2}\d+`', f'`Rev: {version}`', readme)

def readme_update_sms(readme: str, link: str, selector: str) -> str:
    new_tag = '## ARES Mission'
    old_tag = '## Script Management'
    readme = readme.replace(old_tag, new_tag)
    lines = get_readme_splits(readme, new_tag)
    link = link.replace('/create/', '/update/') if selector == 'update' else link
    full_lines = readme.split('\n---\n')
    if lines:
        return '\n---\n'.join([
            sub(r'\(http\:\/\/.*\)', f'({link})', lines[0])
            if new_tag in e else e for e in full_lines
        ])
    template = f'{GLOBAL_ROOT_PATH}/templates/project/README_template.md'
    with open(template, 'rb') as rf:
        template_content = rf.read().decode('utf-8')
    sm_link = get_readme_content(template_content, new_tag).replace('<SM_LINK>', link)
    return '\n---\n'.join([
        f'{e}\n---\n\n{new_tag}\n\n{sm_link}\n'
        if '## Status' in e else e for e in full_lines
    ])

def readme_update_testing_methodology(readme: str, bkms: Dict[str, Any]) -> str:
    lines = get_readme_splits(readme, '## Testing Methodology')
    return '\n---\n'.join([
        '{0}\n\n{1}\n{2}\n{3}\n'.format(
            sub(r'\n+$', '', sub(r'\|.*', '', lines[0])),
            '| **BKM NAME** |    **ID**    | **Description** | **Version** |',
            '|:------------:|:------------:|:---------------:|:-----------:|',
            '\n'.join([
                '| {0} | **[{1}]({2})** | {3} | {4} |'.format(
                    v.get('bkm_name'),
                    v.get('bkm_id'),
                    v.get('bkm_link'),
                    v.get('bkm_objective'),
                    v.get('bkm_version')
                ).replace('\t', '')
                for v in bkms.values()
            ])
        )
        if '## Testing Methodology' in e else e
        for e in readme.split('\n---\n')
    ])

def readme_update_reports(readme: str, log_types: List[LogType]) -> str:
    regexp = r'Log\sFile\s`\w+'
    lines = get_readme_splits(readme, '## Reports')
    reports = [ e for e in lines[0].splitlines() if not search(regexp, e) ]
    content = '\n'.join([ *reports, *[
        f'  - **Log File `{log.filename}`**: {log.description}'
        for log in log_types
    ]])
    return '\n---\n'.join([
        f'{content}\n'
        if '## Reports' in e else e for e in readme.split('\n---\n')
    ])

def readme_update_associates(readme: str, mission: MissionInfo) -> str:
    te_name_item = mission.te_name.replace(';', '\n    - ')
    return '\n---\n'.join([
        '\n{}\n'.format(
            '\n\n'.join([
                '## Associates',
                f'  - **PIC:**\n    - {mission.owner}',
                f'  - **Test Leader:**\n    - {mission.lte_name}',
                f'  - **Tester:**\n    - {te_name_item}',
                f'  - **Developer:**\n    - {mission.developer}'
            ])
        )
        if '## Associates' in e else e for e in readme.split('\n---\n')
    ])

def readme_update_validation(readme: str, te_data: dict) -> str:
    lines = get_readme_splits(readme, '## Validation')
    last_te_name = sorted({
        f'{v.get("datetime")}_{v.get("name")}': v for v in te_data.values()
    })[-1].split('_')[-1]
    last_te_data = te_data.get(last_te_name)
    return '\n---\n'.join([
        '{0}\n{1}\n\n{2}{3}\n'.format(
            sub(r'\-\-\-\-\-\-\-\-\-\-\-\-\:\|\n(?:.|\n)+',
                '------------:|',
                lines[0]),
            '\n'.join([
                '| {0} | {1} | {2} | {3} | {4} |'.format(
                    v.get('name'),
                    v.get('project'),
                    (
                        v.get('datetime')
                        if v.get('datetime').count('-') == 2
                        else sub(r'(\d\d\d\d)(\d\d)(\d\d)', r'\1-\2-\3', v.get('datetime')[:-6])
                    ),
                    (
                        '{+ PASS +}' if v.get('result') == 'pass'
                        else '{- FAIL -}'
                    ),
                    (
                        f'**[Download]({v.get("reports")})**'
                        if v.get('reports') else 'None'
                    )
                ).replace('\t', '')
                for v in te_data.values()
            ]),
            '  - **Latest script has been validated by',
            ' {0} on {1} at {2}.**'.format(
                last_te_data.get('name'),
                last_te_data.get('project'),
                (
                    last_te_data.get('datetime')
                    if last_te_data.get('datetime').count('-') == 2
                    else sub(r'(\d\d\d\d)(\d\d)(\d\d)', r'\1-\2-\3', last_te_data.get('datetime')[:-6])
                )
            )
        )
        if '## Validation' in e else e for e in readme.split('\n---\n')
    ])

def readme_update_coverage(readme: str, coverages: Dict[str, str]) -> str:
    lines = get_readme_splits(readme, '## Coverage')
    regexp = r'\-\-\-\-\-\-\-\-\-\-\-\-\:\|\n(?:.|\n)+'
    return '\n---\n'.join([
        '{0}\n{1}\n'.format(
            sub(regexp, '------------:|', lines[0]),
            '\n'.join([
                f"| {k} | {coverages[k].get('project')} | {coverages[k].get('platform')} |".replace('\t', '')
                for k in coverages
            ])
        )
        if '## Coverage' in e else e for e in readme.split('\n---\n')
    ])

def readme_update_estimate(readme: str, time_saving: str) -> str:
    return '\n---\n'.join([
        sub(r'\`\d+(\.\d+){0,}\s', f'`{time_saving} ', e) + '\n'
        if '## Estimate' in e else e for e in readme.split('\n---\n')
    ])

def markup_url(url: str, regexp: str = 'https?:\/\/\w?') -> str:
    """
    Markup url link as HTML content (click to open a new tab).
    """
    if not search(regexp, url):
        return url
    content = sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', url)
    match = compile(r'\b((?:https?:\/\/)(?:www\.)?(?:[^\s.]+\.)+\w{2,4}\S{0,})\b')
    repl = r'<a style="color: dodgerblue;" target="_blank" href="\1">\1</a>'
    return match.sub(repl, content)

def markup_space(line: str, regexp: str = '^\s+', symbol: str = '&nbsp;') -> str:
    """
    Markup space from passing content for CI pipeline raws.
    First part gonna to replace all the space between color
    code to HTML unicode.
    Second part is going to replace the first string which
    is color code, and then find out space number change it
    to HTML unicode depends on it's quantity.
    """
    compiler = compile(r'\x1B\[\d+;\d+m\s\s+')
    if compiler.search(line):
        for m in compiler.finditer(line):
            (start, end) = compiler.search(line).span()
            line = line[:start] + m.group().replace(' ', symbol) + line[end:]
    compiler = compile(r'^(\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])){1,}')
    match = compiler.search(line)
    if not match:
        return line
    store = match.group()
    line_new = compiler.sub('', line)
    instead = symbol * len(''.join(findall(regexp, line_new)))
    return store + sub(regexp, instead, line_new)

def markup_content(content: str) -> str:
    """
    Markup CI pipeline raws for clearing abnormal ANSI code
    in tmux session, this is going to invoke following func:
    markup_url/markup_space get help to handle in each line.
    """
    rm_strange = '\\u001b(\[(m;\d+h|\d[A-Z]|\>\d+m)|\]\d+)|\\u0007'
    regexp = '\\u001b((\(|\[)([A-Z]|\d+;\d+H|\?\d+\w)|\=|\>|\[.*\\u001b\[K|\[(c|\d+(;(\d+;\d+t|\d+r)|[dJ])))'
    lines = sub(regexp, '', content).splitlines()
    latest = '\n'.join(markup_url(markup_space(e)) for e in lines)
    return sub(rm_strange, '', sub('\n{3,}', '\n\n', latest))
