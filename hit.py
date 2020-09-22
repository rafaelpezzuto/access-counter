import csv

from datetime import datetime
from urllib import parse
from utils import counter_tools, map_helper


class Hit:
    """
    Modelo de dados que representa o acesso a uma página (ação).
    """
    def __init__(self, **kargs):
        # Endereço IP
        self.ip = kargs['ip']

        # Data e horário do acesso
        self.server_time = datetime.strptime(kargs['serverTime'], '%Y-%m-%d %H:%M:%S')

        # Nome do navegador utilizado
        self.browser_name = kargs['browserName'].lower()

        # Versão do navegador utilizado
        self.browser_version = kargs['browserVersion'].lower()

        # ID atribuído a visita (pelo Matomo)
        self.visit_id = kargs['visitId'].lower()

        # ID atribuído ao visitante (pelo Matomo)
        self.visitor_id = kargs['visitorId'].lower()

        # ID da ação (na tabela do Matomo)
        self.action_id = kargs['actionId'].lower()

        # URL da ação
        self.action_name = kargs['actionName'].lower()

        # Extrai parâmetros da URL da ação
        self.action_params = self.extract_params_from_action_name(self.action_name)

        # Cria campos pid, tlng e script a partir dos parâmetros da URL da ação
        self.create_attrs_from_action_params()

        # Extrai tipo de URL
        self.create_item_type_from_pid()

        # Gera um ID de sessão
        self.session_id = counter_tools.generate_session_id(self.ip,
                                                            self.browser_name,
                                                            self.browser_version,
                                                            self.server_time)

    def extract_params_from_action_name(self, action_name: str):
        """
        Extrai parâmetros da URL e cria campos ``pid``, ``tlng`` e ``script``

        :param action_name: URL da ação
        :return: dicionário com os parâmetros extraídos da URL da ação
        """
        return dict(parse.parse_qsl(parse.urlsplit(action_name).query))
