from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint, Index, Date, DateTime
from sqlalchemy.dialects.mysql import BIGINT, BINARY, INTEGER, TINYINT, VARBINARY, VARCHAR
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


Base = declarative_base()


class Journal(Base):
    __tablename__ = 'counter_journal'
    __table_args__ = (UniqueConstraint('collection_acronym', 'print_issn', 'online_issn', 
                                       name='uni_col_print_issn_online_issn'),)
    __table_args__ += (Index('index_print_issn', 'print_issn'),)
    __table_args__ += (Index('index_print_online', 'online_issn'),)

    journal_id = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    collection_acronym = Column(VARCHAR(3), nullable=False)
    title = Column(VARCHAR(255), nullable=False)
    print_issn = Column(VARCHAR(9), nullable=False)
    online_issn = Column(VARCHAR(9), nullable=False)
    uri = Column(VARCHAR(255))
    publisher_name = Column(VARCHAR(255))


class ArticleLang(Base):
    __tablename__ = 'counter_article_lang'

    lang_id = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    name = Column(VARCHAR(3), nullable=False)


class ArticleFormat(Base):
    __tablename__ = 'counter_article_format'

    format_id = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    name = Column(VARCHAR(4), nullable=False)


class Article(Base):
    __tablename__ = 'counter_article'
    __table_args__ = (UniqueConstraint('collection_acronym',
                                       'pid',
                                       'fk_lang_id',
                                       'fk_format_id',
                                       name='uni_col_pid_lang_format'),)
    __table_args__ += (Index('index_col_pid', 'collection_acronym', 'pid'),)
    __table_args__ += (Index('index_col_pid_lang', 'collection_acronym', 'pid', 'fk_lang_id'),)
    __table_args__ += (Index('index_col_pid_format', 'collection_acronym', 'pid', 'fk_format_id'),)

    article_id = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    collection_acronym = Column(VARCHAR(3), nullable=False)
    pid = Column(VARCHAR(23), nullable=False)

    fk_lang_id = Column(INTEGER(unsigned=True), ForeignKey('counter_article_lang.lang_id', name='fk_lang_id'))
    fk_format_id = Column(INTEGER(unsigned=True), ForeignKey('counter_article_format.format_id', name='fk_format_id'))
    fk_journal_id = Column(INTEGER(unsigned=True), ForeignKey('counter_journal.journal_id', name='fk_journal_id'))

    journal = relationship(Journal)


class MetricArticle(Base):
    __tablename__ = 'counter_metric_article'
    __table_args__ = (UniqueConstraint('fk_article_id', 'year_month_day'),)
    __table_args__ += (Index('index_year_month_day', 'year_month_day'),)

    metric_id = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)

    fk_article_id = Column(INTEGER(unsigned=True), ForeignKey('counter_article.article_id', name='fk_article_id'))
    article = relationship(Article)

    year_month_day = Column(Date, nullable=False)
    total_item_requests = Column(Integer, nullable=False)
    total_item_investigations = Column(Integer, nullable=False)
    unique_item_requests = Column(Integer, nullable=False)
    unique_item_investigations = Column(Integer, nullable=False)


class LogAction(Base):
    __tablename__ = 'matomo_log_action'
    __table_args__ = (Index('index_type_hash', 'type', 'hash'),)

    idaction = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    name = Column(VARCHAR(4096))
    hash = Column(INTEGER(unsigned=True), nullable=False)
    type = Column(TINYINT(unsigned=True))
    url_prefix = Column(TINYINT(2))


class LogVisit(Base):
    __tablename__ = 'matomo_log_visit'
    __table_args__ = (Index('index_idsite_idvisitor', 'idsite', 'idvisitor'),)

    idvisit = Column(BIGINT(10, unsigned=True), primary_key=True, autoincrement=True)
    idsite = Column(INTEGER(10, unsigned=True))
    idvisitor = Column(BINARY(8), nullable=False)
    config_browser_name = Column(VARCHAR(10))
    config_browser_version = Column(VARCHAR(20))
    location_ip = Column(VARBINARY(16), nullable=False)


class LogLinkVisitAction(Base):
    __tablename__ = 'matomo_log_link_visit_action'
    __table_args__ = (Index('index_idsite_servertime', 'idsite', 'server_time'),)
    __table_args__ += (Index('index_idvisit', 'idvisit'),)

    idlink_va = Column(BIGINT(10, unsigned=True), primary_key=True, autoincrement=True)
    idsite = Column(INTEGER(unsigned=True), nullable=False)
    idvisitor = Column(BINARY(8), nullable=False)
    server_time = Column(DateTime, nullable=False)

    idaction_url = Column(INTEGER(unsigned=True), ForeignKey('matomo_log_action.idaction', name='idaction_url'))
    action = relationship(LogAction)

    idvisit = Column(BIGINT(10, unsigned=True), ForeignKey('matomo_log_visit.idvisit', name='idvisit'))
    visit = relationship(LogVisit)
