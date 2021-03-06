import logging
import re

from urllib import parse
from utils import values, dicts
from utils import map_actions as ma
from utils import regular_expressions as rege


def article_pid_to_issue_code(pid: str):
    """
    Obtém o código de fascículo de um artigo, a partir de PID

    @param pid: o PID de um artigo
    """
    if pid.startswith('S'):
        if len(pid) == 23:
            return pid[1:18]


def article_pid_to_journal_issn(pid: str, pid_to_issn=None):
    """
    Obtém o ISSN do periódico em que o artigo foi publicado, a partir de seu PID

    @param pid_to_issn: dicionário que mapeia PID a ISSN
    @param pid: o PID de um artigo
    """
    if pid.startswith('S'):
        if len(pid) == 23 and '-' in pid:
            return pid[1:10]

    return sorted(pid_to_issn.get(pid, {''}))[0]


def issue_code_to_journal_issn(pid: str):
    """
    Obtém o código de fascículo de um periódico, a partir de PID

    @param pid: o PID de um artigo
    """
    if not pid.startswith('S'):
        if len(pid) == 17:
            return pid[:10]


def get_url_params_from_action(action: str):
    """
    Extrai parâmetros da URL. Faz limpeza dos parâmetros issn, script, pid e tlng.

    @param action: ação ou URL acessada no Hit
    """
    url_split = parse.urlsplit(action)
    url_qsl = parse.parse_qsl(url_split.query)
    params = dict([(x[0].strip(), x[1].strip()) for x in url_qsl])

    # Faz um tratamento adicional em busca de URLs mal formadas
    if len(url_qsl) == 1 and len(url_qsl[0]) == 2 and 'pid' in url_qsl[0]:
        url_qsl = parse.parse_qsl('='.join(url_qsl[0]))
        params = dict([(x[0].strip(), x[1].strip()) for x in url_qsl])

    # Remove espaços indevidos nas chaves e valores mais importantes
    for k, v in params.items():
        if k in {'issn', 'script', 'pid', 'tlng'}:
            sanitized_value = params.get(k, '').split(' ')[0]

            # Remove ponto final que ocorre em algumas situações
            if sanitized_value.endswith('.'):
                sanitized_value = sanitized_value[:-1]

            # Remove do PID qualquer caractere diferente de S ou dígito
            if k == 'pid':
                sanitized_pid = ''
                for c in sanitized_value:
                    if c.isdigit() or c in {'S', 's', '-', 'x', 'X'}:
                        sanitized_pid += c
                sanitized_value = sanitized_pid

            params[k] = sanitized_value

    return params


def get_url_params_from_action_new_url(action: str):
    action_params = {'pid': '',
                     'acronym': '',
                     'format': 'html',
                     'lang': '',
                     'fragment': '',
                     'resource_ssm_path': ''}

    action_evaluated = action
    if not action_evaluated.startswith('http'):
        action_evaluated = ''.join(['http://', action_evaluated])

    action_parsed = parse.urlparse(action_evaluated)
    params = dict(parse.parse_qsl(action_parsed.query))
    for k, v in params.items():
        if k in action_params:
            action_params[k] = v

    action_params['fragment'] = action_parsed.fragment
    action_params['acronym'], action_params['pid'] = _get_acronym_and_pid_from_action_new_url(action)

    return action_params


def get_attrs_from_ssm_path(ssm_path: str):
    data = {}

    match = re.search(rege.REGEX_NEW_SCL_RAW_DETAIL, ssm_path)
    if match and len(match.groups()) == 3:
        data['issn'] = match.group(1).upper()
        data['pid'] = match.group(2)
        data['file'] = match.group(3)
        if data['file'].endswith('.pdf'):
            data['format'] = values.FORMAT_PDF

    return data


def get_hit_type_new_url(action: str):
    for pattern in [rege.REGEX_NEW_SCL_JOURNAL_ARTICLE,
                    rege.REGEX_NEW_SCL_RAW]:
        if re.search(pattern, action):
            return ma.HIT_TYPE_ARTICLE

    for pattern in [rege.REGEX_NEW_SCL_JOURNAL_FEED,
                    rege.REGEX_NEW_SCL_JOURNAL_GRID,
                    rege.REGEX_NEW_SCL_JOURNAL_TOC,
                    rege.REGEX_NEW_SCL_JOURNAL]:
        if re.search(pattern, action):
            return ma.HIT_TYPE_JOURNAL

    for pattern in [rege.REGEX_NEW_SCL_JOURNALS_ALFAPHETIC,
                    rege.REGEX_NEW_SCL_JOURNALS_THEMATIC]:
        if re.search(pattern, action):
            return ma.HIT_TYPE_PLATFORM

    return ma.HIT_TYPE_OTHERS


def get_hit_type(hit):
    """
    Obtém o tipo de Hit

    @param hit: um objeto Hit
    @return: o tipo de Hit
    """
    hit_type = None

    # Tenta obter o tipo de Hit a partir do PID
    if hit.pid:
        hit_type = _get_hit_type_from_pid_or_issn(hit.pid, hit.issn)

    if not hit_type or hit_type == ma.HIT_TYPE_OTHERS:
        hit_type = _get_hit_type_from_content_type(hit.content_type)

    return hit_type


def _get_hit_type_from_pid_or_issn(pid: str, issn: str):
    """
    Obtém o tipo de hit conforme o PID ou o ISSN

    @param pid: atributo pid de um Hit
    @return: o tipo de Hit, se PID foi identificado, -1 caso contrário
    """
    if re.match(rege.REGEX_ARTICLE_PID, pid):
        return ma.HIT_TYPE_ARTICLE
    elif re.match(rege.REGEX_ISSUE_PID, pid):
        return ma.HIT_TYPE_ISSUE
    elif re.match(rege.REGEX_JOURNAL_PID, pid):
        return ma.HIT_TYPE_JOURNAL
    elif re.match(rege.REGEX_JOURNAL_PID, issn):
        return ma.HIT_TYPE_JOURNAL

    return ma.HIT_TYPE_OTHERS


def _get_hit_type_from_content_type(content_type: int):
    """
    Obtém o tipo de Hit a partir do contéudo já definido

    @param content_type: um inteiro que representa o tipo de conteúdo
    @return: o tipo de Hit
    """
    if content_type < 50:
        return ma.HIT_TYPE_ARTICLE
    elif content_type < 100:
        return ma.HIT_TYPE_ISSUE
    elif content_type < 150:
        return ma.HIT_TYPE_JOURNAL
    elif content_type < 200:
        return ma.HIT_TYPE_PLATFORM

    return ma.HIT_TYPE_OTHERS


def get_journal_acronym(hit, issn2acronym: dict):
    """
    Obtém acrônimo de periódico
     1. Tenta obtê-lo por meio do parâmetro ISSN no dicionário
     2. Tenta obtê-lo por meio do formato da ACTION

    @param hit: um Hit
    @param issn2acronym: um dicionário de acrônimo para ISSN
    @return: acrônimo de um periódico, caso identificado
    """
    acronym = ''

    if hit.issn:
        acronym = issn2acronym.get(hit.collection, {}).get(hit.issn, '')

    if not acronym:
        acronym = _get_journal_acronym_from_action(hit.action_name)
    return acronym


def _get_journal_acronym_from_action(action: str):
    """
    Obtém acrônimo de periódico com base no conteúdo de uma action (URL)

    @param action: Hit.action
    @return: acrônimo de um periódico, caso identificado
    """
    for pattern in {rege.REGEX_JOURNAL_IMG_REVISTAS,
                    rege.REGEX_JOURNAL_FBPE,
                    rege.REGEX_JOURNAL_EDITORIAL_BOARD,
                    rege.REGEX_JOURNAL_ABOUT,
                    rege.REGEX_JOURNAL_INSTRUCTIONS,
                    rege.REGEX_JOURNAL_SUBSCRIPTION,
                    rege.REGEX_JOURNAL_REVISTAS}:
        matched_acronym = re.match(pattern, action)
        if matched_acronym:
            if len(matched_acronym.groups()) == 1:
                return matched_acronym.group(1)

    matched_acronym = re.match(rege.REGEX_ARTICLE_PDF_ACRONYM, action)
    if matched_acronym:
        return matched_acronym.group(1)


def _get_acronym_and_pid_from_action_new_url(action: str):
    match = re.search(rege.REGEX_NEW_SCL_JOURNAL_ARTICLE, action)
    if match:
        if len(match.groups()) == 2:
            return match.group(1), match.group(2)
    return '', ''


def get_year_of_publication_new_url(hit, pid2yop: dict):
    return pid2yop.get(hit.collection, {}).get(hit.pid, {}).get('publication_year', '')


def get_year_of_publication(hit, pid2yop: dict):
    """
    Obtém o ano de publicação (yop) associado ao PID.

    @param hit: Hit ao qual o yop é atribuído
    @param pid2yop: dicionário que mapeia PID a ano de publicação (YOP)
    @return: o ano de publicação associado ao PID
    """
    yop = pid2yop.get(hit.collection, {}).get(hit.pid, {}).get('publication_year', '')

    if not yop:
        yop = _get_year_of_publication_from_pid(hit.pid)

    return yop


def _get_year_of_publication_from_pid(pid):
    """
    Obtém o Ano de Publicação (YOP) de um artigo a partir do PID.
    É útil nas situações em que o PID não foi encontrado no dicionário pid-dates.

    @param pid: PID
    @return: o ano de publicação associado ao PID
    """
    yop = ''
    matched_yop = re.search(rege.REGEX_ARTICLE_PID_YOP, pid)
    if matched_yop:
        if len(matched_yop.groups()) == 1:
            yop = matched_yop.group(1)

    if not yop or not yop.isdigit() or len(yop) != 4:
        yop = ''

    return yop


def get_pid_from_pdf_path(hit, pdf2pid: dict):
    """
    Obtém o PID de um artigo a partir de dicionário de caminho de pdf para PID

    @param hit: um Hit a arquivo PDF
    @param pdf2pid: um dicionário de caminho de pdf --> PID
    @return: o PID associado ao PDF ou uma string vazia
    """
    url_parsed = parse.urlparse(hit.action_name)

    # Obtém caminho pdf
    pdf_path = url_parsed.path

    # Verifica se caminho é realmente de pdf
    if not re.search(rege.REGEX_ARTICLE_PDF_PATH, pdf_path):
        matched_pdf_path = re.search(rege.REGEX_ARTICLE_PDF_PATH, pdf_path)
        if matched_pdf_path:
            pdf_path = matched_pdf_path.group()
        else:
            return ''

    # Verifica se há prefixo scielo.br no caminho do pdf
    if re.search(rege.REGEX_ARTICLE_PDF_FULL_PATH, pdf_path):
        matched_pdf_full_path = re.search(rege.REGEX_ARTICLE_PDF_FULL_PATH, pdf_path)
        if matched_pdf_full_path and len(matched_pdf_full_path.groups()) == 2:
            pdf_path = matched_pdf_full_path.group(2)

    # Remove a barra final, caso exista
    # Todas as chaves do dicionário pdf2pid não contêm a barra final
    if pdf_path.endswith('/'):
        pdf_path = pdf_path[:-1]

    # Adicoina extensão .pdf, caso não esteja presente
    # Todas as chaves do dicionário pdf2pid contêm a extensão pdf
    if not pdf_path.endswith('.pdf'):
        pdf_path += '.pdf'

    extracted_pid = sorted(pdf2pid.get(hit.collection, {}).get(pdf_path, set()))
    if extracted_pid:
        return extracted_pid[0]

    logging.debug('PDF não foi associado a PID: (%s, %s)' % (pdf_path, hit.action_name))
    return ''


def get_issn(hit, acronym2pid: dict):
    """
    Obtém o ISSN a partir de um PID, de um dicionário Acrônimo:PID ou da ActionName
    
    @param hit: um Hit
    @param acronym2pid: um dicionário Acrônimo:PID
    @return: ISSN ou string vazia 
    """
    if re.search(rege.REGEX_JOURNAL_PID, hit.pid):
        return hit.pid
    elif re.search(rege.REGEX_ISSUE_PID, hit.pid):
        return issue_code_to_journal_issn(hit.pid)
    elif re.search(rege.REGEX_ARTICLE_PID, hit.pid):
        return article_pid_to_journal_issn(hit.pid)

    # Tenta obter ISSN a partir de trecho pid_(ISSN) de url
    if hit.content_type == ma.HIT_CONTENT_JOURNAL_SERIAL:
        matched_script_sci_serial_issn = re.match(rege.REGEX_JOURNAL_SCRIPT_SCI_SERIAL, hit.action_name)
        if matched_script_sci_serial_issn:
            if len(matched_script_sci_serial_issn.groups()) == 1:
                return matched_script_sci_serial_issn.group(1)

    # Tenta obter ISSN a partir de trecho pid_(ISSN) de url
    if hit.content_type == ma.HIT_CONTENT_JOURNAL_ISSUES:
        matched_script_sci_issues_issn = re.match(rege.REGEX_JOURNAL_SCRIPT_SCI_ISSUES, hit.action_name)
        if matched_script_sci_issues_issn:
            if len(matched_script_sci_issues_issn.groups()) == 1:
                return matched_script_sci_issues_issn.group(1)

    return acronym2pid.get(hit.collection, {}).get(hit.acronym, [''])[0]


def get_content_type_new_url(hit):
    action_lowered = hit.action_name.lower()
    if re.search(rege.REGEX_NEW_SCL_JOURNAL_ARTICLE_ABSTRACT, action_lowered):
        return ma.HIT_CONTENT_NEW_SCL_ARTICLE_ABSTRACT

    if re.search(rege.REGEX_NEW_SCL_JOURNAL_ARTICLE, action_lowered):
        if hit.format == 'html':
            if 'fragment' in hit.__dict__.keys():
                if hit.fragment == 'modaltutors':
                    return ma.HIT_CONTENT_NEW_SCL_ARTICLE_AUTHORS
                if hit.fragment == 'modaltablesfigures':
                    return ma.HIT_CONTENT_NEW_SCL_ARTICLE_TABLES_AND_FIGURES
                if hit.fragment == 'modaldownloads':
                    return ma.HIT_CONTENT_NEW_SCL_ARTICLE_REQUEST_PDF
                if hit.fragment == 'modalarticles':
                    return ma.HIT_CONTENT_NEW_SCL_ARTICLE_HOW_TO_CITE
                if hit.fragment == 'modalversionstranslations':
                    return ma.HIT_CONTENT_NEW_SCL_ARTICLE_TRANSLATE
            return ma.HIT_CONTENT_NEW_SCL_ARTICLE_HTML

        if hit.format == 'xml':
            return ma.HIT_CONTENT_NEW_SCL_ARTICLE_XML

        if hit.format == 'pdf':
            return ma.HIT_CONTENT_NEW_SCL_ARTICLE_PDF

    if re.search(rege.REGEX_NEW_SCL_RAW, action_lowered):
        match = re.search(rege.REGEX_NEW_SCL_RAW_DETAIL, action_lowered)
        if match and len(match.groups()) == 3:
            if '.pdf' in match.group(3):
                return ma.HIT_CONTENT_NEW_SCL_ARTICLE_PDF

    if re.search(rege.REGEX_NEW_SCL_JOURNAL_FEED, action_lowered):
        return ma.HIT_CONTENT_NEW_SCL_JOURNAL_FEED

    if re.search(rege.REGEX_NEW_SCL_JOURNAL_GRID, action_lowered):
        return ma.HIT_CONTENT_NEW_SCL_JOURNAL_GRID

    if re.search(rege.REGEX_NEW_SCL_JOURNAL_TOC, action_lowered):
        return ma.HIT_CONTENT_NEW_SCL_JOURNAL_TOC

    if re.search(rege.REGEX_NEW_SCL_JOURNAL, action_lowered):
        return ma.HIT_CONTENT_NEW_SCL_JOURNAL

    if re.search(rege.REGEX_NEW_SCL_JOURNALS_ALFAPHETIC, action_lowered):
        return ma.HIT_CONTENT_NEW_SCL_JOURNALS_ALPHABETIC

    if re.search(rege.REGEX_NEW_SCL_JOURNALS_THEMATIC, action_lowered):
        return ma.HIT_CONTENT_NEW_SCL_JOURNALS_THEMATIC

    return ma.HIT_CONTENT_OTHERS


def get_content_type(hit):
    possible_domains = dicts.collection_to_domain.get(hit.collection, [])

    for scl_domain in possible_domains:
        # É domínio/scielo.php
        if re.search(ma.ACTION_SCLBR_SCLPHP.format(scl_domain), hit.action_name):
            # Caso possua parâmero script
            if hit.script:
                return dicts.script_to_hit_content.get(hit.script, ma.HIT_CONTENT_OTHERS)

            # Caso não possua parâmetro script
            if '?download' in hit.action_name:
                return ma.HIT_CONTENT_ARTICLE_DOWNLOAD_CITATION
            if 'script_sci_issues' in hit.action_name:
                return ma.HIT_CONTENT_JOURNAL_ISSUES
            if 'script_sci_serial' in hit.action_name:
                return ma.HIT_CONTENT_JOURNAL_SERIAL
            return ma.HIT_CONTENT_PLATFORM_MAIN_PAGE

        # É domínio/article_plus.php? + pid={}
        if re.search(ma.ACTION_SCLBR_ARTICLE_PLUS.format(scl_domain), hit.action_name):
            return ma.HIT_CONTENT_ARTICLE_PLUS

        # É domínio/pdf/ + arquivo.pdf
        if re.search(ma.ACTION_SCLBR_PDF.format(scl_domain), hit.action_name):
            return ma.HIT_CONTENT_ARTICLE_PDF

        # É domínio/pdf/readcube/epdf.php? + pid={}
        if re.search(ma.ACTION_SCLBR_READCUBE_EPDF.format(scl_domain), hit.action_name):
            return ma.HIT_CONTENT_ARTICLE_EXTERNAL_PDF

        # É domínio/scieloorg/php/{} + pid={}
        if re.search(ma.ACTION_SCLBR_SCLORG_PHP.format(scl_domain), hit.action_name):
            if 'articlexml' in hit.action_name:
                return ma.HIT_CONTENT_ARTICLE_ARTICLE_XML
            if 'citedscielo' in hit.action_name:
                return ma.HIT_CONTENT_ARTICLE_CITEDSCIELO
            if 'reference' in hit.action_name:
                return ma.HIT_CONTENT_ARTICLE_REFERENCE_LIST
            if 'related' in hit.action_name:
                return ma.HIT_CONTENT_ARTICLE_RELATED
            if 'translate' in hit.action_name:
                return ma.HIT_CONTENT_ARTICLE_TRANSLATE

        # É domínio/rss? + pid={}
        if re.search(ma.ACTION_SCLBR_RSS.format(scl_domain), hit.action_name):
            if re.search(rege.REGEX_ISSUE_PID, hit.pid):
                return ma.HIT_CONTENT_ISSUE_RSS
            if re.search(rege.REGEX_JOURNAL_PID, hit.pid):
                return ma.HIT_CONTENT_JOURNAL_RSS

        # É domínio/revistas/ + página ou arquivo
        if re.search(ma.ACTION_SCLBR_REVISTAS.format(scl_domain), hit.action_name):
            if 'aboutj.htm' in hit.action_name:
                return ma.HIT_CONTENT_JOURNAL_ABOUT
            if 'edboard.htm' in hit.action_name:
                return ma.HIT_CONTENT_JOURNAL_EDITORIAL
            if 'instruc.htm' in hit.action_name:
                return ma.HIT_CONTENT_JOURNAL_INSTRUCTIONS
            if 'subscrp.htm' in hit.action_name:
                return ma.HIT_CONTENT_JOURNAL_SUBSCRIPTION
            return ma.HIT_CONTENT_JOURNAL_REVISTAS

        # É domínio/google_metrics/get_h5_m5.php? + issn={}
        if re.search(ma.ACTION_SCLBR_GOOGLE_METRICS_H5_M5.format(scl_domain), hit.action_name):
            return ma.HIT_CONTENT_JOURNAL_GOOGLE_METRICS

        # É domínio/img/{fbpe ou revistas} + acrônimo
        if re.search(ma.ACTION_SCLBR_IMG.format(scl_domain), hit.action_name):
            if 'fbpe' in hit.action_name:
                return ma.HIT_CONTENT_JOURNAL_IMG_FBPE
            if 'revistas' in hit.action_name:
                return ma.HIT_CONTENT_JOURNAL_IMG_REVISTAS

        # É domínio/statjournal.php? + issn={}
        if re.search(ma.ACTION_SCLBR_STATJOURNAL.format(scl_domain), hit.action_name):
            return ma.HIT_CONTENT_JOURNAL_STAT

        # É domínio/avaliacao
        if re.search(ma.ACTION_SCLBR_AVALIACAO.format(scl_domain), hit.action_name):
            return ma.HIT_CONTENT_PLATFORM_EVALUATION

        # É domínio/equipe
        if re.search(ma.ACTION_SCLBR_EQUIPE.format(scl_domain), hit.action_name):
            return ma.HIT_CONTENT_PLATFORM_TEAM

        # É domínio (scielo.br, scielo.org.ar, ...)
        if re.search(scl_domain, hit.action_name):
            return ma.HIT_CONTENT_PLATFORM_HOME

    return ma.HIT_CONTENT_OTHERS


def get_language_new_url(hit, pid2format2lang: dict):
    return pid2format2lang.get(hit.collection, {}).get(hit.pid, {}).get('default', values.LANGUAGE_UNDEFINED)


def get_language(hit, pid2format2lang: dict):
    """
    Obtém o idioma do recurso acessado com base em dicionário de PIDs, formato e idiomas

    @param hit: um Hit
    @param pid2format2lang: um dicionário que mapeia PID aos seus respectivos formatos e idiomas
    @return: o idioma associado ao Hit
    """
    if hit.pid not in pid2format2lang.get(hit.collection, {}):
        logging.debug('PID não encontrado em PID-Formato-Idiomas (PID: %s, FMT: %s, ActionName: %s)' % (hit.pid, hit.format, hit.action_name))
        return values.LANGUAGE_UNDEFINED

    if hit.lang in pid2format2lang.get(hit.collection, {}).get(hit.pid, {}).get(hit.format, set()):
        return hit.lang
    else:
        logging.debug('Idioma não consta em lista de idiomas associáveis ao PID e formato (PID: %s, FMT: %s, Lang: %s)' % (hit.pid, hit.format, hit.lang))
        return pid2format2lang.get(hit.collection, {}).get(hit.pid, {}).get('default', values.LANGUAGE_UNDEFINED)


def get_format(hit):
    """
    Obtém o formato do recurso acessado.

    @param hit: um Hit
    @return: o formato associado ao Hit
    """
    if hit.content_type:
        if hit.content_type in {ma.HIT_CONTENT_ARTICLE_PDF,
                                ma.HIT_CONTENT_ARTICLE_EXTERNAL_PDF} or re.search(rege.REGEX_PDF,
                                                                                  hit.action_name) or re.search(rege.REGEX_ARTICLE_PDF_PATH,
                                                                                                                hit.action_name):
            hit_format = values.FORMAT_PDF
        else:
            hit_format = values.FORMAT_HTML
    else:
        hit_format = values.DEFAULT_FORMAT

    return hit_format


def is_new_url_format(action: str):
    for pattern in [rege.REGEX_NEW_SCL_JOURNAL_ARTICLE_ABSTRACT,
                    rege.REGEX_NEW_SCL_JOURNAL_ARTICLE,
                    rege.REGEX_NEW_SCL_JOURNAL_FEED,
                    rege.REGEX_NEW_SCL_JOURNAL_GRID,
                    rege.REGEX_NEW_SCL_JOURNAL_TOC,
                    rege.REGEX_NEW_SCL_JOURNAL,
                    rege.REGEX_NEW_SCL_JOURNALS_ALFAPHETIC,
                    rege.REGEX_NEW_SCL_JOURNALS_THEMATIC,
                    rege.REGEX_NEW_SCL_RAW]:
        if re.search(pattern, action):
            return True

    return False


def get_content_type_preprints(hit):
    unquoted_action = parse.unquote(hit.action_name)

    for pattern in [rege.REGEX_PREPRINT_VIEW_ABSTRACT,
                    rege.REGEX_PREPRINT_DOCUMENT_ABSTRACT,
                    rege.REGEX_PREPRINT_VERSION_ABSTRACT]:
        if re.search(pattern, unquoted_action):
            return ma.HIT_CONTENT_TYPE_PREPRINT_ABSTRACT

    for pattern in [rege.REGEX_PREPRINT_VIEW_PDF,
                    rege.REGEX_PREPRINT_DOWNLOAD_PDF,
                    rege.REGEX_PREPRINT_DOCUMENT_DOWNLOAD_PDF,
                    rege.REGEX_PREPRINT_VERSION_DOWNLOAD_PDF]:
        if re.search(pattern, unquoted_action):
            return ma.HIT_CONTENT_TYPE_PREPRINT_PDF

    return ma.HIT_CONTENT_OTHERS


def get_format_preprints(hit):
    if hit.content_type == ma.HIT_CONTENT_TYPE_PREPRINT_ABSTRACT:
        return values.FORMAT_HTML
    elif hit.content_type == ma.HIT_CONTENT_TYPE_PREPRINT_PDF:
        return values.FORMAT_PDF
    else:
        return ''


def get_pid_preprint(hit):
    unquoted_action = parse.unquote(hit.action_name)

    for pattern in [rege.REGEX_PREPRINT_VIEW_ABSTRACT,
                    rege.REGEX_PREPRINT_DOCUMENT_ABSTRACT,
                    rege.REGEX_PREPRINT_VERSION_ABSTRACT,
                    rege.REGEX_PREPRINT_VIEW_PDF,
                    rege.REGEX_PREPRINT_DOWNLOAD_PDF,
                    rege.REGEX_PREPRINT_DOCUMENT_DOWNLOAD_PDF,
                    rege.REGEX_PREPRINT_VERSION_DOWNLOAD_PDF]:
        match = re.search(pattern, unquoted_action)
        if match:
            return match.group(1)


def get_language_preprints(hit, pid2format2lang: dict):
    return pid2format2lang.get(hit.collection, {}).get(hit.pid, {}).get('default', values.LANGUAGE_UNDEFINED)


def get_year_of_publication_preprints(hit, pid2yop: dict):
    return pid2yop.get(hit.collection, {}).get(hit.pid, {}).get('publication_year', '')


def get_hit_type_ssp(action: str):
    for pattern in [rege.REGEX_SSP_JOURNAL_ARTICLE_HTML,
                    rege.REGEX_SSP_JOURNAL_ARTICLE_PDF,
                    rege.REGEX_SSP_JOURNAL_ARTICLE_MEDIA_ASSETS]:
        if re.search(pattern, action):
            return ma.HIT_TYPE_ARTICLE

    for pattern in [rege.REGEX_SSP_JOURNAL_ABOUT,
                    rege.REGEX_SSP_JOURNAL_GRID,
                    rege.REGEX_SSP_JOURNAL_FEED]:
        if re.search(pattern, action):
            return ma.HIT_TYPE_JOURNAL

    for pattern in [rege.REGEX_SSP_JOURNAL_ISSUE,
                    rege.REGEX_SSP_JOURNAL_FEED_ISSUE]:
        if re.search(pattern, action):
            return ma.HIT_TYPE_ISSUE

    for pattern in [rege.REGEX_SSP_PLATFORM_ABOUT,
                    rege.REGEX_SSP_JOURNALS_THEMATIC,
                    rege.REGEX_SSP_JOURNALS_ALPHABETIC]:
        if re.search(pattern, action):
            return ma.HIT_TYPE_PLATFORM

    if re.search(rege.REGEX_SSP_PLATFORM, action):
        return ma.HIT_TYPE_PLATFORM

    return ma.HIT_TYPE_OTHERS


def get_content_type_ssp_url(hit):
    action_lowered = hit.action_name.lower()
    if re.search(rege.REGEX_SSP_JOURNAL_ARTICLE_HTML, action_lowered):
        return ma.HIT_CONTENT_SSP_ARTICLE_HTML

    if re.search(rege.REGEX_SSP_JOURNAL_ARTICLE_PDF, action_lowered):
        return ma.HIT_CONTENT_SSP_ARTICLE_PDF

    if re.search(rege.REGEX_SSP_JOURNAL_ARTICLE_MEDIA_ASSETS, action_lowered):
        if action_lowered.endswith('.pdf'):
            return ma.HIT_CONTENT_SSP_ARTICLE_PDF

    if re.search(rege.REGEX_SSP_JOURNAL_ISSUE, action_lowered):
        return ma.HIT_CONTENT_SSP_ISSUE

    if re.search(rege.REGEX_SSP_JOURNAL_FEED_ISSUE, action_lowered):
        return ma.HIT_CONTENT_SSP_ISSUE_RSS

    if re.search(rege.REGEX_SSP_JOURNAL_FEED, action_lowered):
        return ma.HIT_CONTENT_SSP_JOURNAL_RSS

    if re.search(rege.REGEX_SSP_JOURNAL_GRID, action_lowered):
        return ma.HIT_CONTENT_SSP_JOURNAL_ISSUES

    if re.search(rege.REGEX_SSP_JOURNAL_ABOUT, action_lowered):
        return ma.HIT_CONTENT_SSP_JOURNAL_ABOUT

    if re.search(rege.REGEX_SSP_JOURNAL, action_lowered):
        return ma.HIT_CONTENT_SSP_JOURNAL_MAIN_PAGE

    if re.search(rege.REGEX_SSP_JOURNALS_ALPHABETIC, action_lowered):
        return ma.HIT_CONTENT_SSP_PLATFORM_LIST_JOURNALS_ALPHABETIC

    if re.search(rege.REGEX_SSP_JOURNALS_THEMATIC, action_lowered):
        return ma.HIT_CONTENT_SSP_PLATFORM_LIST_JOURNALS_THEMATIC

    if re.search(rege.REGEX_SSP_PLATFORM_ABOUT, action_lowered):
        return ma.HIT_CONTENT_SSP_PLATFORM_ABOUT

    return ma.HIT_CONTENT_OTHERS


def get_url_params_from_action_ssp_url(action: str):
    action_params = {'pid': '',
                     'acronym': '',
                     'format': '',
                     'lang': '',
                     'resource_ssm_path': ''}

    action_evaluated = action
    if not action_evaluated.startswith('http'):
        action_evaluated = ''.join(['http://', action_evaluated])

    action_parsed = parse.urlparse(action_evaluated)
    if 'resource_ssm_path' in action_evaluated:
        get_url_params_from_ssp_resource_path(action_params, action_parsed.query)
    else:
        get_url_params_from_ssp_path(action_params, action_parsed.path)

    return action_params


def get_url_params_from_ssp_path(action_params, ssp_path):
    for k, v in {values.FORMAT_HTML: rege.REGEX_SSP_JOURNAL_ARTICLE_HTML_DETAILS,
                 values.FORMAT_PDF: rege.REGEX_SSP_JOURNAL_ARTICLE_PDF_DETAILS}.items():
        match = re.search(v, ssp_path)

        if match:
            action_params['format'] = k
            action_params['acronym'] = match.group(1)
            action_params['year_vol_issue'] = match.group(2)
            action_params['pages'] = match.group(3)
            action_params['lang'] = match.group(4)

            return

    path_match_assets = re.match(rege.REGEX_SSP_JOURNAL_ARTICLE_MEDIA_ASSETS_DETAILS, ssp_path)
    if path_match_assets:
        action_params['acronym'] = path_match_assets.group(1)
        action_params['year_vol_issue'] = path_match_assets.group(2)
        action_params['file'] = path_match_assets.group(3)

        if ssp_path.endswith('.pdf'):
            action_params['format'] = values.FORMAT_PDF


def get_url_params_from_ssp_resource_path(action_params, ssp_path_query):
    resource_path = dict(parse.parse_qsl(ssp_path_query)).get('resource_ssm_path', '')
    match = re.search(rege.REGEX_SSP_JOURNAL_ARTICLE_MEDIA_ASSETS_DETAILS, resource_path)
    if match:
        action_params['acronym'] = match.group(1)
        action_params['year_vol_issue'] = match.group(2)
        action_params['file'] = match.group(3)
        action_params['resource_ssm_path'] = resource_path

        if ssp_path_query.endswith('.pdf'):
            action_params['format'] = values.FORMAT_PDF


def get_ssp_pid(action_params):
    artificial_pid = ':'.join([action_params.get('acronym', ''),
                               action_params.get('year_vol_issue', '')])

    if 'pages' in action_params:
        return ':'.join([artificial_pid, action_params.get('pages', '')]).lower()

    if 'file' in action_params:
        return ':'.join([artificial_pid, action_params.get('file', '')]).lower()


# ToDo: Integrar com dicionário ainda a ser construído
def get_language_ssp(pid: str, pid2format2lang: dict):
    return pid2format2lang.get('spa', {}).get(pid, values.LANGUAGE_UNDEFINED)


# ToDo: Integrar com dicionário ainda a ser construído
def get_year_of_publication_ssp_pid(pid: str):
    match = re.search(rege.REGEX_SSP_JOURNAL_ARTICLE_YEAR, pid)
    if match:
        return match.group(1)
    return ''
