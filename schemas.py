from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field


class TeamSchema(BaseModel):
    id: Optional[Union[int, str]] = Field(default=0, description="ID único do time")
    nome: str = Field(default="Time", description="Nome completo da equipe")
    logo: Optional[str] = Field(default="", description="URL do escudo/logo")
    sigla: Optional[str] = Field(default="", description="Sigla ou abreviação da equipe")


class LeagueSchema(BaseModel):
    id: Optional[Union[int, str]] = Field(default=0, description="ID da competição")
    nome: str = Field(default="Campeonato", description="Nome do campeonato")
    pais: Optional[str] = Field(default="Mundo", description="País do campeonato")
    logo: Optional[str] = Field(default="", description="URL do logo do campeonato")
    rodada: Optional[str] = Field(default="Rodada Regular", description="Rodada ou fase")


class ScoreSchema(BaseModel):
    mandante: Optional[int] = Field(default=None, description="Gols do mandante")
    visitante: Optional[int] = Field(default=None, description="Gols do visitante")


class MatchInfoSchema(BaseModel):
    id: Union[int, str] = Field(description="ID do evento")
    data_hora: str = Field(description="Data e hora ISO 8601")
    horario: str = Field(default="16:00", description="Horário de início (HH:MM)")
    status: str = Field(default="SCHEDULED", description="Status canônico: SCHEDULED, LIVE, FINISHED")
    status_descricao: str = Field(default="Agendado", description="Descrição amigável do status")
    estadio: Optional[str] = Field(default="Estádio Oficial", description="Nome do estádio")
    cidade: Optional[str] = Field(default="", description="Cidade da partida")
    placar: ScoreSchema = Field(default_factory=ScoreSchema, description="Placar atual da partida")
    tempo_decorrido: Optional[Union[int, str]] = Field(default=None, description="Minuto decorrido")
    mandante: TeamSchema = Field(default_factory=TeamSchema)
    visitante: TeamSchema = Field(default_factory=TeamSchema)


class MatchSchema(BaseModel):
    """
    Schema canônico universal para partidas de futebol ingeridas pela cadeia em cascata.
    Compatível integralmente com o front-end, Odds Pedia e Gemini AI.
    """
    id: Union[int, str] = Field(description="ID único do confronto")
    data: Optional[str] = Field(default="", description="Data da partida YYYY-MM-DD")
    data_hora: str = Field(description="Data e hora em ISO 8601")
    horario: str = Field(default="16:00", description="Horário formatado em HH:MM")
    status: str = Field(default="SCHEDULED", description="Status canônico: SCHEDULED, LIVE, FINISHED")
    status_descricao: str = Field(default="Agendado", description="Descrição legível em PT-BR")
    estadio: Optional[str] = Field(default="Estádio Oficial", description="Estádio do evento")
    cidade: Optional[str] = Field(default="", description="Cidade")
    placar: ScoreSchema = Field(default_factory=ScoreSchema)
    tempo_decorrido: Optional[Union[int, str]] = Field(default=None)
    mandante: TeamSchema = Field(default_factory=TeamSchema)
    visitante: TeamSchema = Field(default_factory=TeamSchema)
    campeonato: LeagueSchema = Field(default_factory=LeagueSchema)
    estatisticas: Optional[Dict[str, Any]] = Field(default_factory=dict)
    provedor: str = Field(default="Owls Insight", description="Nome do provedor que forneceu os dados")
    provedores_integrados: List[str] = Field(default_factory=list, description="Lista de provedores que enriqueceram o registro")

    def to_dict(self) -> Dict[str, Any]:
        """Converte o MatchSchema para o dicionário padrão esperado pelo orquestrador."""
        return self.model_dump()
