"""parsivel: parsivel_leitura (depende das tabelas do nucleo)

Revision ID: parsivel_0001
Revises:
Create Date: 2026-10-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "parsivel_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("parsivel",)
depends_on: Union[str, Sequence[str], None] = "nucleo_0001"


def upgrade() -> None:
    op.create_table('parsivel_leitura',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('equipamento_id', sa.Integer(), nullable=False),
    sa.Column('envio_id', sa.Integer(), nullable=False),
    sa.Column('tempo', sa.DateTime(), nullable=False, comment='do nome do arquivo, relogio do XLink, sem fuso'),
    sa.Column('arquivo', sa.Text(), nullable=False),
    sa.Column('corrompido', sa.Boolean(), nullable=False, comment='sem 90, 91 ou 93 completos'),
    sa.Column('intensidade_chuva', sa.Float(), nullable=True, comment='01, mm/h'),
    sa.Column('chuva_acumulada', sa.Float(), nullable=True, comment='02, mm desde que o sensor ligou'),
    sa.Column('codigo_synop_wawa', sa.Integer(), nullable=True, comment='03, tabela 4680'),
    sa.Column('codigo_synop_ww', sa.Integer(), nullable=True, comment='04, tabela 4677'),
    sa.Column('codigo_metar', sa.Text(), nullable=True, comment='05, tabela 4678'),
    sa.Column('refletividade', sa.Float(), nullable=True, comment='07, dBZ (-9.999 = sem gota)'),
    sa.Column('visibilidade_mor', sa.Float(), nullable=True, comment='08, m'),
    sa.Column('intervalo_amostragem', sa.Float(), nullable=True, comment='09, s'),
    sa.Column('n_particulas', sa.Float(), nullable=True, comment='11, particulas validadas'),
    sa.Column('temperatura_sensor', sa.Float(), nullable=True, comment='12, C, dentro da carcaca'),
    sa.Column('tensao', sa.Float(), nullable=True, comment='17, V'),
    sa.Column('inicio_medida', sa.Text(), nullable=True, comment='19, DD.MM.YYYY_hh:mm:ss'),
    sa.Column('hora_sensor', sa.Text(), nullable=True, comment='20, hh:mm:ss'),
    sa.Column('data_sensor', sa.Text(), nullable=True, comment='21, DD.MM.YYYY'),
    sa.Column('chuva_absoluta', sa.Float(), nullable=True, comment='24, mm (no XLink: chuva da leitura)'),
    sa.Column('codigo_erro', sa.Text(), nullable=True, comment='25'),
    sa.Column('intensidade_16bit_30', sa.Float(), nullable=True, comment='30, mm/h'),
    sa.Column('intensidade_16bit_1200', sa.Float(), nullable=True, comment='31, mm/h'),
    sa.Column('chuva_acumulada_16bit', sa.Float(), nullable=True, comment='32, mm'),
    sa.Column('energia_cinetica', sa.Float(), nullable=True, comment='34, J/(m2 h)'),
    sa.Column('n_particulas_total', sa.Float(), nullable=True, comment='60, inclusive as nao validadas'),
    sa.Column('n_d', sa.LargeBinary(), nullable=True, comment='90, 32 x float32 LE, log10(1/(m3 mm))'),
    sa.Column('v_d', sa.LargeBinary(), nullable=True, comment='91, 32 x float32 LE, m/s'),
    sa.Column('raw', sa.LargeBinary(), nullable=True, comment='93, zlib(32x32 int16 LE) [velocidade, diametro]'),
    sa.Column('amplitude_laser', sa.Float(), nullable=True, comment='10'),
    sa.Column('corrente_aquecimento', sa.Float(), nullable=True, comment='16, A'),
    sa.Column('status_sensor', sa.Integer(), nullable=True, comment='18, 0 OK, 1 lentes sujas, 2 sem medida, 3 laser danificado'),
    sa.Column('temperatura_placa', sa.Float(), nullable=True, comment='26, C'),
    sa.Column('temperatura_cabeca_direita', sa.Float(), nullable=True, comment='27, C'),
    sa.Column('temperatura_cabeca_esquerda', sa.Float(), nullable=True, comment='28, C'),
    sa.Column('numero_serie', sa.Text(), nullable=True, comment='13'),
    sa.Column('firmware_iop', sa.Text(), nullable=True, comment='14'),
    sa.Column('firmware_dsp', sa.Text(), nullable=True, comment='15'),
    sa.ForeignKeyConstraint(['envio_id'], ['envio.id'], name=op.f('fk_parsivel_leitura_envio_id_envio')),
    sa.ForeignKeyConstraint(['equipamento_id'], ['equipamento.id'], name=op.f('fk_parsivel_leitura_equipamento_id_equipamento')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_parsivel_leitura')),
    sa.UniqueConstraint('equipamento_id', 'tempo', name=op.f('uq_parsivel_leitura_equipamento_id_tempo'))
    )
    op.create_index(op.f('ix_parsivel_leitura_envio_id'), 'parsivel_leitura', ['envio_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_parsivel_leitura_envio_id'), table_name='parsivel_leitura')
    op.drop_table('parsivel_leitura')
