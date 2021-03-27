import logging

from datetime import datetime
from socket import inet_ntoa
from utils import map_actions as at
from libs import lib_hit, lib_counter


class Hit:
    """
    Classe que representa o acesso a uma página (ação)
    """
    def __init__(self, **kargs):
        # Endereço IP
        self.ip = kargs.get('ip', '')

        # Localização associada ao IP
        self.latitude = kargs.get('latitude', '')
        self.longitude = kargs.get('longitude', '')

        # Data e horário do acesso
        if isinstance(kargs.get('serverTime', ''), datetime):
            self.server_time = kargs.get('serverTime')
        else:
            self.server_time = datetime.strptime(kargs.get('serverTime', ''), '%Y-%m-%d %H:%M:%S')

        # Nome do navegador utilizado
        self.browser_name = kargs.get('browserName', '').lower()

        # Versão do navegador utilizado
        self.browser_version = kargs.get('browserVersion', '').lower()

        # URL da ação
        self.action_name = kargs.get('actionName', '')

    def _is_from_local_network(self):
        if self.latitude in {'', 'NULL'} or not self.latitude:
            return True
        if self.longitude in {'', 'NULL'} or not self.longitude:
            return True
        return False

    def _is_null_action(self):
        if self.action_name == '' or not self.action_name or self.action_name == 'null':
            return True
        return False

    def is_valid_hit(self):
        # Verifica se Hit é da rede local
        if self._is_from_local_network():
            logging.debug('Hit ignorado. Acesso é da rede local (IP: %s, ActionName: %s)' % (self.ip, self.action_name))
            return False

        # Verifica se Hit é relacionado a ação nula
        if self._is_null_action():
            logging.debug('Hit ignorado. Atributo action_name está vazio (IP: %s, ActionName: %s)' % (self.ip, self.action_name))
            return False

        return True

    def is_trackable_hit(self, flag_include_other_hit_types=False):
        # Ignora Hits não artigo (a depender de flag_include_other_hit_types)
        if not flag_include_other_hit_types:
            if self.hit_type != at.HIT_TYPE_ARTICLE:
                return False

        # Verifica se Hit possui conteúdo indefinido
        if self.content_type == at.HIT_CONTENT_OTHERS:
            logging.debug('Hit ignorado. Conteúdo não é rastreável (HitType: %s, ActionName: %s)' % (self.hit_type, self.action_name))
            return False

        # Verifica se Hit possui tipo indefinido
        if self.hit_type == at.HIT_CONTENT_OTHERS:
            logging.debug('Hit ignorado. Tipo não foi determinado (IP: %s, ActionName: %s)' % (self.ip, self.action_name))
            return False

        if not self.issn and self.hit_type in {at.HIT_TYPE_ARTICLE,
                                               at.HIT_TYPE_ISSUE,
                                               at.HIT_TYPE_JOURNAL}:
            logging.debug('Hit ignorado. ISSN não está definido (HitType: %s, ActionName: %s' % (self.hit_type, self.action_name))
            return False

        # Verifica se Hit possui um PID válido
        if self.hit_type == at.HIT_TYPE_ARTICLE and not self.pid:
            logging.debug('Hit ignorado. PID não está definido (HitType: %s, ActionName: %s' % (self.hit_type, self.action_name))
            return False

        return True


class HitManager:
    """
    Classe que gerencia objetos Hit
    """
    def __init__(self, path_pdf_to_pid, issn_to_acronym, pid_to_format_lang, pid_to_yop, persist_on_database, flag_include_other_hit_types=False):
        self.hits = {'article': {}, 'issue': {}, 'journal': {}, 'platform': {}, 'others': {}}

        # Dicionários para tratamento de PID
        self.pdf_path_to_pid = path_pdf_to_pid
        self.issn_to_acronym = issn_to_acronym
        self.pid_to_format_lang = pid_to_format_lang
        self.pid_to_yop = pid_to_yop
        self.pid_to_issn = {}

        # Gera um dicionário reverso de acrônimos
        self.acronym_to_issn = self._generate_acronym_to_issn()

        # Flag para incluir na contagem outros tipos de Hit (Issue, Journal, Platform)
        self.flag_include_other_hit_types = flag_include_other_hit_types

        # Utilizada para analisar corretude de lista de Hits e de Métricas
        self.persist_on_database = persist_on_database

    def _generate_acronym_to_issn(self):
        """
        Obtém um dicionário Acrônimo:ISSN a partir de ISSN:Acrônimo
        """
        new_dict = {}
        for col, key_value in self.issn_to_acronym.items():
            if col not in new_dict:
                new_dict[col] = {}

            for k, v in key_value.items():
                if v not in new_dict[col]:
                    new_dict[col][v] = []

                if k not in new_dict[col][v]:
                    new_dict[col][v].append(k)
        return new_dict

    def create_hit(self, row, mode):
        """
        Cria objeto Hit

        @param row: um objeto LogLinkVisitAction
        @param mode: possui o valor `file` se crição é a partir de arquivo ou `sql` se é a partir de base de dados
        @return: um objeto Hit
        """
        if mode == 'database':
            row = {'serverTime': row.server_time,
                   'browserName': row.visit.config_browser_name,
                   'browserVersion': row.visit.config_browser_version,
                   'ip': inet_ntoa(row.visit.location_ip),
                   'latitude': row.visit.location_latitude,
                   'longitude': row.visit.location_longitude}

        new_hit = Hit(**row)

        if new_hit.is_valid_hit():
            # Caso Hit tenha um conteúdo válido, Obtém outros atributos
            self.set_hit_attrs(new_hit)

            # Caso Hit seja rastreável (associável a um Periódico, Fascículo ou Artigo)
            if new_hit.is_trackable_hit(self.flag_include_other_hit_types):
                return new_hit

        # Caso Hit seja ou inválido ou não rastreável
        return

    def set_hit_attrs(self, hit):
        """
        Seta os atributos de um Hit usando dados do Hit Manager

        @hit: um objeto Hit
        """
        # Gera um ID de sessão
        hit.session_id = lib_counter.generate_session_id(hit.ip,
                                                         hit.browser_name,
                                                         hit.browser_version,
                                                         hit.server_time)

        # Obtém coleção ao qual o Hit pertence
        hit.collection = lib_hit.get_collection(hit.action_name.lower())

        if lib_hit.is_new_url_format(hit.action_name.lower()):
            self._set_hit_attrs_new_url(hit)
        else:
            self._set_hit_attrs_classic_url(hit)

    def _set_hit_attrs_new_url(self, hit):
        hit.action_params = lib_hit.get_url_params_from_action_new_url(hit.action_name)

        hit.pid = hit.action_params['pid']
        hit.acronym = hit.action_params['acronym'].lower()
        hit.format = hit.action_params['format'].lower()
        hit.lang = hit.action_params['lang'].lower()

        if hit.action_params['resource_ssm_path']:
            hit.action_params.update(lib_hit.get_attrs_from_ssm_path(hit.action_params['resource_ssm_path']))
            hit.issn = hit.action_params['issn'].upper()
            hit.format = hit.action_params['format'].lower()
            hit.pid = hit.action_params['pid']

        hit.content_type = lib_hit.get_content_type_new_url(hit)
        hit.hit_type = lib_hit.get_hit_type_new_url(hit.action_name.lower())

        if hit.hit_type == at.HIT_TYPE_ARTICLE:
            # ToDo: ao atualizar dicionários, esse tratamento não será mais necessário
            collection_to_check = 'scl' if hit.collection == 'nbr' else hit.collection

            if 'issn' not in hit.__dict__.keys() or not hit.issn:
                hit.issn = self.acronym_to_issn.get(collection_to_check, {}).get(hit.acronym, [''])[0].upper()

            if hit.pid not in self.pid_to_issn:
                if hit.issn:
                    self.pid_to_issn[hit.pid] = {hit.issn}
            else:
                self.pid_to_issn[hit.pid].add(hit.issn)
                if len(self.pid_to_issn[hit.pid]) > 2:
                    logging.warning('PID %s está associado a mais de dois ISSNs: %s' %(hit.pid, self.pid_to_issn[hit.pid]))

            # ToDo: atualizar os dicionários de ano de publicação e idiomas oficiais suportados
            hit.yop = lib_hit.get_year_of_publication(hit, self.pid_to_yop)
            hit.lang = lib_hit.get_language(hit, self.pid_to_format_lang)

    def _set_hit_attrs_classic_url(self, hit):
        hit.action_name = hit.action_name.lower()

        # Extrai parâmetros da URL de ação de um Hit
        hit.action_params = lib_hit.get_url_params_from_action(hit.action_name)

        # Obtém dados a partir dos parâmetros extraídos (relacionados ao formato de URL clássica)
        hit.pid = hit.action_params.get('pid', '').upper()
        hit.lang = hit.action_params.get('tlng', '')
        hit.script = hit.action_params.get('script', '')
        hit.issn = hit.action_params.get('issn', '').upper()

        # Obtém PID do Hit, caso parâmetro de URL não tenha conseguido obtê-lo
        if not hit.pid:
            hit.pid = lib_hit.get_pid_from_pdf_path(hit, self.pdf_path_to_pid)

        # Obtém o tipo de conteúdo associado ao Hit
        hit.content_type = lib_hit.get_content_type(hit)

        # Obtém o formato do Hit (PDF ou HTML)
        hit.format = lib_hit.get_format(hit)

        # Obtém o tipo de Hit
        hit.hit_type = lib_hit.get_hit_type(hit)

        hit.issn = lib_hit.article_pid_to_journal_issn(hit.pid, self.pid_to_issn)
        hit.acronym = lib_hit.get_journal_acronym(hit, self.issn_to_acronym)
        if not hit.issn:
            hit.issn = lib_hit.get_issn(hit, self.acronym_to_issn)

        if hit.hit_type == at.HIT_TYPE_ARTICLE:
            hit.yop = lib_hit.get_year_of_publication(hit, self.pid_to_yop)
            hit.lang = lib_hit.get_language(hit, self.pid_to_format_lang)

    def reset(self):
        """
        Limpa registros do HitManager
        """
        self.hits = {'article': {}, 'issue': {}, 'journal': {}, 'platform': {}, 'others': {}}

    def add_hit(self, hit: Hit):
        if hit.hit_type == at.HIT_TYPE_ARTICLE:
            key = (hit.pid, hit.format, hit.lang, hit.latitude, hit.longitude, hit.yop)
            group = 'article'
        elif hit.hit_type == at.HIT_TYPE_ISSUE:
            issue_code = hit.pid
            key = (hit.issn, issue_code, hit.latitude, hit.longitude)
            group = 'issue'
        elif hit.hit_type == at.HIT_TYPE_JOURNAL:
            key = (hit.issn, hit.latitude, hit.longitude)
            group = 'journal'
        elif hit.hit_type == at.HIT_TYPE_PLATFORM:
            key = ('scielo', hit.latitude, hit.longitude)
            group = 'platform'
        else:
            key = ('others', hit.latitude, hit.longitude)
            group = 'others'

        if hit.session_id not in self.hits[group]:
            self.hits[group][hit.session_id] = {}

        if key not in self.hits[group][hit.session_id]:
            self.hits[group][hit.session_id][key] = []

        self.hits[group][hit.session_id][key].append(hit)

    def remove_double_clicks(self):
        """
        Remove cliques duplos. São comparados os hits dentro de uma sessão.
        """
        for group, session_key_hits in self.hits.items():
            for session, key_hits in session_key_hits.items():
                for key, hits in key_hits.items():
                    cleaned_hits = []

                    if len(hits) > 1:
                        sorted_hits = sorted(hits, key=lambda x: x.server_time)

                        for i in range(len(sorted_hits) - 1):
                            past_hit = sorted_hits[i]
                            current_hit = sorted_hits[i + 1]

                            if not lib_counter.is_double_click(group, past_hit, current_hit):
                                cleaned_hits.append(past_hit)
                                if i + 2 == len(sorted_hits):
                                    cleaned_hits.append(current_hit)
                            elif i + 2 == len(sorted_hits):
                                cleaned_hits.append(current_hit)
                    else:
                        cleaned_hits.extend(hits)

                    key_hits[key] = cleaned_hits
