from __future__ import annotations

from collections import defaultdict
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Union

from sqlalchemy.orm import Session, aliased
from sqlalchemy.orm.query import Query
from sqlalchemy.sql.expression import or_

from .db import DB
from .models import (
    Issue,
    IssueInstance,
    IssueInstanceSharedTextAssoc,
    SharedText,
    SharedTextKind,
)


FilenameText = aliased(SharedText)
CallableText = aliased(SharedText)
CallerText = aliased(SharedText)
CalleeText = aliased(SharedText)
MessageText = aliased(SharedText)


class Filter(Enum):
    codes = "codes"
    callables = "callables"
    file_names = "file_names"
    trace_length_to_sources = "trace_length_to_sources"
    trace_length_to_sinks = "trace_length_to_sinks"
    any_features = "any_features"
    all_features = "all_features"


class IssueQueryBuilder:
    def __init__(self, database: DB, current_run_id: int):
        self.db = database
        self.current_run_id = current_run_id
        self.issue_filters: Dict[
            Filter, Set[Tuple[Union[int, str, Tuple[int, int, ...]], ...]]
        ] = defaultdict(set)
        self.breadcrumb_filters: Dict[Filter, List[str]] = defaultdict(list)

    def get(self) -> List:
        with self.db.make_session() as session:
            query = self._get_session_query(session)
            for filter_type, filter_conditions in self.issue_filters.items():
                if filter_type == Filter.codes:
                    column = Issue.code
                elif filter_type == Filter.callables:
                    column = CallableText.contents
                elif filter_type == Filter.file_names:
                    column = FilenameText.contents
                elif filter_type == Filter.trace_length_to_sources:
                    column = IssueInstance.min_trace_length_to_sources
                elif filter_type == Filter.trace_length_to_sinks:
                    column = IssueInstance.min_trace_length_to_sinks

                for filter_condition in filter_conditions:
                    if (
                        filter_type == Filter.trace_length_to_sources
                        or filter_type == Filter.trace_length_to_sinks
                    ):
                        if filter_condition[0]:
                            query = query.filter(column >= filter_condition[0])
                        if filter_condition[1]:
                            query = query.filter(column <= filter_condition[1])
                    else:
                        query = query.filter(
                            or_(*[column.like(item) for item in filter_condition])
                        )
            issues = list(
                query.join(Issue, IssueInstance.issue_id == Issue.id).join(
                    MessageText, MessageText.id == IssueInstance.message_id
                )
            )

            any_feature_set = set()
            all_feature_set = set()
            for filter_type, filter_condition in self.breadcrumb_filters.items():
                if filter_type == Filter.any_features:
                    any_feature_set |= set(filter_condition)
                else:
                    all_feature_set |= set(filter_condition)
                features_list = [
                    self._get_leaves_issue_instance(
                        session,
                        int(issue.id),
                        # pyre-fixme[6]: Expected `SharedTextKind` for 3rd param but got
                        #  `(cls: SharedTextKind) -> Any`.
                        SharedTextKind.FEATURE,
                    )
                    for issue in issues
                ]
                for issue, features in zip(issues, features_list):
                    if any_feature_set and not (features & any_feature_set):
                        issues.remove(issue)
                    elif all_feature_set and not (
                        features & all_feature_set == all_feature_set
                    ):
                        issues.remove(issue)
            return issues

    def where_codes_is_any_of(self, codes: List[int]) -> IssueQueryBuilder:
        self.issue_filters[Filter.codes].add(tuple(codes))
        return self

    def where_callables_is_any_of(self, callables: List[str]) -> IssueQueryBuilder:
        self.issue_filters[Filter.callables].add(tuple(callables))
        return self

    def where_file_names_is_any_of(self, file_names: List[str]) -> IssueQueryBuilder:
        self.issue_filters[Filter.file_names].add(tuple(file_names))
        return self

    def where_trace_length_to_sinks(
        self, minimum: Optional[int] = None, maximum: Optional[int] = None
    ) -> IssueQueryBuilder:
        self.issue_filters[Filter.trace_length_to_sinks].add((minimum, maximum))
        return self

    def where_trace_length_to_sources(
        self, minimum: Optional[int] = None, maximum: Optional[int] = None
    ) -> IssueQueryBuilder:
        self.issue_filters[Filter.trace_length_to_sources].add((minimum, maximum))
        return self

    def where_any_features(self, features: List[str]) -> IssueQueryBuilder:
        self.breadcrumb_filters[Filter.any_features] += features
        return self

    def where_all_features(self, features: List[str]) -> IssueQueryBuilder:
        self.breadcrumb_filters[Filter.all_features] += features
        return self

    def sources(self, issues) -> List[Set[str]]:
        with self.db.make_session() as session:
            return [
                self._get_leaves_issue_instance(
                    session,
                    int(issue.id),
                    # pyre-fixme[6]: Expected `SharedTextKind` for 3rd param but got
                    #  `(cls: SharedTextKind) -> Any`.
                    SharedTextKind.SINK,
                )
                for issue in issues
            ]

    def sinks(self, issues) -> List[Set[str]]:
        with self.db.make_session() as session:
            return [
                self._get_leaves_issue_instance(
                    session,
                    int(issue.id),
                    # pyre-fixme[6]: Expected `SharedTextKind` for 3rd param but got
                    #  `(cls: SharedTextKind) -> Any`.
                    SharedTextKind.SOURCE,
                )
                for issue in issues
            ]

    def features(self, issues) -> List[Set[str]]:
        with self.db.make_session() as session:
            return [
                self._get_leaves_issue_instance(
                    session,
                    int(issue.id),
                    # pyre-fixme[6]: Expected `SharedTextKind` for 3rd param but got
                    #  `(cls: SharedTextKind) -> Any`.
                    SharedTextKind.FEATURE,
                )
                for issue in issues
            ]

    def _get_session_query(self, session: Session) -> Query:
        return (
            session.query(
                IssueInstance.id,
                FilenameText.contents.label("filename"),
                IssueInstance.location,
                Issue.code,
                CallableText.contents.label("callable"),
                MessageText.contents.label("message"),
                IssueInstance.min_trace_length_to_sources,
                IssueInstance.min_trace_length_to_sinks,
            )
            .filter(IssueInstance.run_id == self.current_run_id)
            .join(FilenameText, FilenameText.id == IssueInstance.filename_id)
            .join(CallableText, CallableText.id == IssueInstance.callable_id)
        )

    def _get_leaves_issue_instance(
        self, session: Session, issue_instance_id: int, kind: SharedTextKind
    ) -> Set[str]:
        message_ids = [
            int(id)
            for id, in session.query(SharedText.id)
            .distinct(SharedText.id)
            .join(
                IssueInstanceSharedTextAssoc,
                SharedText.id == IssueInstanceSharedTextAssoc.shared_text_id,
            )
            .filter(IssueInstanceSharedTextAssoc.issue_instance_id == issue_instance_id)
            .filter(SharedText.kind == kind)
        ]
        return self._leaf_dict_lookups(message_ids, kind, session)

    def _leaf_dict_lookups(
        self, message_ids: List[int], kind: SharedTextKind, session: Session
    ) -> Set[str]:
        if kind == SharedTextKind.SOURCE:
            leaf_dict = {
                int(id): contents
                for id, contents in session.query(
                    SharedText.id, SharedText.contents
                ).filter(SharedText.kind == kind)
            }
        elif kind == SharedTextKind.SINK:
            leaf_dict = {
                int(id): contents
                for id, contents in session.query(
                    SharedText.id, SharedText.contents
                ).filter(SharedText.kind == kind)
            }
        else:
            leaf_dict = {
                int(id): contents
                for id, contents in session.query(
                    SharedText.id, SharedText.contents
                ).filter(SharedText.kind == kind)
            }
        return {leaf_dict[id] for id in message_ids if id in leaf_dict}
