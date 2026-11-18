"""Публичные модели ответов и данные: всё, что отдают клиенты и сервер.

Модули `diarysdk.models.<модуль>` остаются корректным адресом; здесь те же классы
одним списком.
"""

from diarysdk.models.auth import (
    Captcha,
    LoginCaptcha,
    LoginMfa,
    LoginStep,
    TokenInfo,
    TokenResponse,
)
from diarysdk.models.avatar import Avatar
from diarysdk.models.certificates import Certificate
from diarysdk.models.common import ClassUnit, Material, PersonName, SchoolBrief, Subject
from diarysdk.models.curriculum import (
    ControlWork,
    Curriculum,
    CurriculumSection,
    CurriculumSubject,
    CurriculumSubjectWeek,
    CurriculumWeek,
    ProgramLesson,
    ProgramModule,
    ProgramTopic,
    SubjectTopic,
    TopicResult,
)
from diarysdk.models.exams import Exam
from diarysdk.models.files import DiaryFile
from diarysdk.models.homework import Attachment, Homework
from diarysdk.models.identity import (
    Address,
    Contact,
    ContactUpdate,
    Document,
    DocumentAct,
    DocumentAttachment,
    Education,
    EducationClass,
    GradeBook,
    Health,
    Identity,
    IdentityBase,
    IdentityPerson,
    Representative,
    Specialty,
    StudyGroup,
)
from diarysdk.models.lessons import Lesson, LessonTeacher, Theme
from diarysdk.models.marks import (
    AcademicDebt,
    ClassResults,
    FinalMark,
    Mark,
    MarkDetail,
    MarkDistribution,
    MarkLesson,
)
from diarysdk.models.me import Me, MePerson, Section, TokenExpiry
from diarysdk.models.notifications import Notification, NotificationHomework, NotificationMark
from diarysdk.models.parent import Child, JournalAck, ParentMe
from diarysdk.models.periods import PeriodDay
from diarysdk.models.rating import Rating, RatingEntry, RatingMe, RatingPoint, SubjectRating
from diarysdk.models.schedule import HomeworkBrief, HomeworkCounts, ScheduleItem
from diarysdk.models.school import Branch, School, SchoolTeacher, Teacher
from diarysdk.models.settings import Settings, SettingsTheme, SettingsThemeUpdate, SettingsUpdate
from diarysdk.models.subjects import (
    Period,
    SubjectDetail,
    SubjectDetailPeriod,
    SubjectSummary,
    Target,
    TargetPath,
)

__all__ = [
    "AcademicDebt",
    "Address",
    "Attachment",
    "Avatar",
    "Branch",
    "Captcha",
    "Certificate",
    "Child",
    "ClassResults",
    "ClassUnit",
    "Contact",
    "ContactUpdate",
    "ControlWork",
    "Curriculum",
    "CurriculumSection",
    "CurriculumSubject",
    "CurriculumSubjectWeek",
    "CurriculumWeek",
    "DiaryFile",
    "Document",
    "DocumentAct",
    "DocumentAttachment",
    "Education",
    "EducationClass",
    "Exam",
    "FinalMark",
    "GradeBook",
    "Health",
    "Homework",
    "HomeworkBrief",
    "HomeworkCounts",
    "Identity",
    "IdentityBase",
    "IdentityPerson",
    "JournalAck",
    "Lesson",
    "LessonTeacher",
    "LoginCaptcha",
    "LoginMfa",
    "LoginStep",
    "Mark",
    "MarkDetail",
    "MarkDistribution",
    "MarkLesson",
    "Material",
    "Me",
    "MePerson",
    "Notification",
    "NotificationHomework",
    "NotificationMark",
    "ParentMe",
    "Period",
    "PeriodDay",
    "PersonName",
    "ProgramLesson",
    "ProgramModule",
    "ProgramTopic",
    "Rating",
    "RatingEntry",
    "RatingMe",
    "RatingPoint",
    "Representative",
    "ScheduleItem",
    "School",
    "SchoolBrief",
    "SchoolTeacher",
    "Section",
    "Settings",
    "SettingsTheme",
    "SettingsThemeUpdate",
    "SettingsUpdate",
    "Specialty",
    "StudyGroup",
    "Subject",
    "SubjectDetail",
    "SubjectDetailPeriod",
    "SubjectRating",
    "SubjectSummary",
    "SubjectTopic",
    "Target",
    "TargetPath",
    "Teacher",
    "Theme",
    "TokenExpiry",
    "TokenInfo",
    "TokenResponse",
    "TopicResult",
]
