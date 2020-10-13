import argparse
import csv
import datetime
import logging
import os
import pickle

from counter import CounterStat
from hit import HitManager
from socket import inet_ntoa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from time import time
from utils import db_tools, pid_tools
from utils.sql_declarative import Article, MetricArticle


def get_dates(date: str):
    """
    Obtém lista de dias para extrair informações do Matomo

    @param date: uma data em formato de `YYYY-MM-DD` ou um período no formato `YYYY-MM-DD,YYYY-MM-DD`
    @return: lista de data(s) em formato de objeto `datetime`
    """
    if ',' not in date:
        return [datetime.datetime.strptime(date, '%Y-%m-%d')]
    else:
        dates = date.split(',')
        if len(dates) == 2:
            start = datetime.datetime.strptime(dates[0], '%Y-%m-%d')
            end = datetime.datetime.strptime(dates[1], '%Y-%m-%d') + datetime.timedelta(days=1)
            return [start + datetime.timedelta(days=x) for x in range(0, (end - start).days)]


def get_log_files(path_log_files: str):
    """
    Obtém lista de caminhos de arquivos log com dados previamente extraídos do Matomo

    @param path_log_files: arquivo de log ou pasta com arquivos de log
    @return: lista de caminhos de arquivo(s) log
    """
    log_files = []
    if os.path.isfile(path_log_files):
        log_files.append(path_log_files)
    elif os.path.isdir(path_log_files):
        log_files.extend([os.path.join(os.path.abspath(path_log_files), f) for f in os.listdir(path_log_files)])
    return log_files


def update_metrics(metric_article, data):
    """
    Atualiza valores de métricas COUNTER para um registro.
    Caso registro seja novo, considera os valores em data.
    Caso registro já existe, faz soma valores atuais com valores novos

    @param metric_article: registro de `MetricArticle`
    @param data: dados a serem adicionados ou atribuídos ao registro
    """
    keys = ['total_item_investigations',
            'total_item_requests',
            'unique_item_investigations',
            'unique_item_requests']

    for k in keys:
        current_value = metric_article.__getattribute__(k)
        if current_value:
            metric_article.__setattr__(k, current_value + data[k])
        else:
            metric_article.__setattr__(k, data[k])


def save_metrics_into_db(metrics: dict, db_session, collection: str):
    """
    Persiste métricas COUNTER na base de dados Matomo

    @param metrics: um dicionário contendo métricas COUNTER a serem persistidas
    @param db_session: sessão com banco de dados
    @param collection: acrônimo de coleção
    """
    for pid_key, pid_data in metrics.items():
        # Obtém o ISSN associado ao PID
        issn = pid_tools.article_to_journal(pid_key)

        for ymd in pid_data:
            try:
                # Procura periódico na base de dados
                existing_journal = db_tools.get_journal(db_session=db_session, issn=issn, collection=collection)

                try:
                    # Procura artigo na base de dados
                    existing_article = db_tools.get_article(db_session=db_session, pid=pid_key, collection=collection)

                except NoResultFound:
                    # Cria um novo artigo caso artigo não exista na base de dados
                    new_article = Article()
                    new_article.collection_acronym = collection
                    new_article.fk_journal_id = existing_journal.journal_id
                    new_article.pid = pid_key

                    db_session.add(new_article)
                    db_session.flush()

                    existing_article = new_article

                try:
                    existing_metric_article = db_tools.get_metric_article(db_session=db_session,
                                                                          year_month_day=ymd,
                                                                          article_id=existing_article.article_id)
                    update_metrics(existing_metric_article, pid_data[ymd])
                    logging.info('Atualizado {}'.format(existing_metric_article.metric_id))

                except NoResultFound:
                    # Cria um novo registro de métrica, caso não exista na base de dados
                    new_metric_article = MetricArticle()
                    new_metric_article.fk_article_id = existing_article.article_id
                    new_metric_article.year_month_day = ymd

                    update_metrics(new_metric_article, pid_data[ymd])

                    db_session.add(new_metric_article)
                    logging.info('Adicionado {}-{}'.format(new_metric_article.fk_article_id,
                                                           new_metric_article.year_month_day))

                db_session.flush()

            except NoResultFound as e:
                logging.error('Nenhum periódico foi localizado na base de dados: {}, {}'.format(issn, e))
            except MultipleResultsFound as e:
                logging.error('Mais de um periódico foi localizado na base de dados: {}, {}'.format(issn, e))
            except IntegrityError as e:
                db_session.rollback()
                logging.error('Artigo já está na base: {}'.format(e))


def run_for_log_file(log_file: str, hit_manager: HitManager, db_session, collection):
    with open(log_file) as f:
        csv_file = csv.DictReader(f, delimiter='\t')

        past_ip = ''
        for log_row in csv_file:
            current_ip = log_row.get('ip', '')

            if past_ip != current_ip:
                run_counter_routines(hit_manager=hit_manager,
                                     db_session=db_session,
                                     collection=collection)
                past_ip = current_ip

            hit = hit_manager.create_hit_from_log_line(**log_row)
            if hit:
                hit_manager.add_hit(hit)


def run_for_matomo_db(date, hit_manager, idsite, db_session, collection):
    results = db_tools.get_matomo_logs_for_date(db_session=db_session,
                                                idsite=idsite,
                                                date=date)

    past_ip = ''
    for row in results:
        current_ip = inet_ntoa(row.visit.location_ip)

        if past_ip != current_ip:
            run_counter_routines(hit_manager=hit_manager,
                                 db_session=db_session,
                                 collection=collection)
            past_ip = current_ip

        hit = hit_manager.create_hit_from_sql_data(row)
        if hit:
            hit_manager.add_hit(hit)


def run_counter_routines(hit_manager: HitManager, db_session, collection):
    """
    Executa métodos COUNTER para remover cliques-duplos, contar acessos por PID e extraír métricas.
    Ao final, salva resultados (métricas) na base de dados Matomo

    @param hit_manager: um objeto `HitManager` que gerencia objetos `Hit`
    @param db_session: um objeto `Session` para conexão com base de dados Matomo
    @param collection: acrônimo de coleção
    """
    hit_manager.remove_double_clicks(hit_manager.session_to_actions)
    hit_manager.count_hits_by_pid()

    cs = CounterStat()
    cs.populate_counter(hit_manager.pid_to_hits)
    save_metrics_into_db(metrics=cs.articles_metrics, db_session=db_session, collection=collection)
    hit_manager.reset()


def main():
    usage = 'Extrai informações de log no formato COUNTER R5'
    parser = argparse.ArgumentParser(usage)

    parser.add_argument(
        '-c', '--collection',
        dest='collection',
        default='scl',
        help='Acrônimo da coleção objeto de extração de métricas'
    )

    parser.add_argument(
        '-i', '--idsite',
        dest='idsite',
        required=True,
        help='Identificador Matomo do site do qual as informações serão extraídas'
    )

    parser.add_argument(
        '-p', '--pdf_paths',
        dest='pdf_to_pid',
        help='Dicionário que mapeia caminho de PDF a PID'
    )

    parser.add_argument(
        '-a', '--acronyms',
        dest='issn_to_acronym',
        help='Dicionário que mapeia ISSN a acrônimo'
    )

    parser.add_argument(
        '-u', '--matomo_db_uri',
        required=True,
        dest='matomo_db_uri',
        help='String de conexão a base SQL Matomo no formato mysql://username:password@host1:port/database'
    )

    parser.add_argument(
        '--logging_level',
        choices=['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'],
        dest='logging_level',
        default='INFO',
        help='Nível de log'
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '-d', '--period',
        dest='period',
        help='Periódo da qual os dados serão extraídos do Matomo. Caso esteja no formato YYYY-MM-DD,YYYY-MM-DD, '
             'o período entre a primeira e segunda datas será considerado. Caso esteja no formato YYYY-MM-DD, '
             'apenas os dados do dia indicado serão extraídos'
    )
    group.add_argument(
        '-l', '--logs',
        dest='logs',
        default=[],
        help='Carrega dados a partir de uma pasta com arquivos de log ou um único arquivo de log '
             'prevhit_managerente extraído(s) do Matomo'
    )

    params = parser.parse_args()

    logging.basicConfig(level=params.logging_level)

    time_start = time()

    logging.info('Carregando dicionário de caminhos de PDF --> PID')
    pdf_to_pid = pickle.load(open(params.pdf_to_pid, 'rb'))

    logging.info('Carregando dicionário de ISSN --> acrônimo de periódico')
    issn_to_acronym = pickle.load(open(params.issn_to_acronym, 'rb'))

    db_session = db_tools.get_db_session(params.matomo_db_uri)
    hit_manager = HitManager(path_pdf_to_pid=pdf_to_pid, issn_to_acronym=issn_to_acronym)

    if params.logs:
        logging.info('Iniciado para usar arquivos de log')
        log_files = get_log_files(params.logs)
        for lf in log_files:
            logging.info('Extraindo dados do arquivo {}'.format(lf))
            hit_manager.reset()

            run_for_log_file(log_file=lf,
                             hit_manager=hit_manager,
                             db_session=db_session,
                             collection=params.collection)

    else:
        logging.info('Iniciado para coletar dados diretamente de banco de dados Matomo')
        dates = get_dates(date=params.period)
        for date in dates:
            logging.info('Extraindo dados para data {}'.format(date.strftime('%Y-%m-%d')))
            hit_manager.reset()

            run_for_matomo_db(date=date,
                              hit_manager=hit_manager,
                              idsite=params.idsite,
                              db_session=db_session,
                              collection=params.collection)

    time_end = time()
    logging.info('Durou %.2f segundos' % (time_end - time_start))


if __name__ == '__main__':
    main()
