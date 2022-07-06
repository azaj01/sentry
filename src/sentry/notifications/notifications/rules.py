from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping, MutableMapping, Optional, Sequence, TypedDict

import pytz

from sentry.db.models import Model
from sentry.models import Release, ReleaseCommit, Team, User, UserOption
from sentry.notifications.notifications.base import ProjectNotification
from sentry.notifications.types import ActionTargetType, NotificationSettingTypes
from sentry.notifications.utils import (
    get_commits,
    get_group_settings_link,
    get_integration_link,
    get_interface_list,
    get_rules,
    has_alert_integration,
    has_integrations,
)
from sentry.notifications.utils.participants import get_send_to
from sentry.plugins.base.structs import Notification
from sentry.types.integrations import ExternalProviders
from sentry.utils import metrics
from sentry.utils.http import absolute_uri, urlencode

logger = logging.getLogger(__name__)


class AlertRuleNotification(ProjectNotification):
    message_builder = "IssueNotificationMessageBuilder"
    metrics_key = "issue_alert"
    notification_setting_type = NotificationSettingTypes.ISSUE_ALERTS
    template_path = "sentry/emails/error"

    def __init__(
        self,
        notification: Notification,
        target_type: ActionTargetType,
        target_identifier: int | None = None,
    ) -> None:
        event = notification.event
        group = event.group
        project = group.project
        super().__init__(project)
        self.group = group
        self.event = event
        self.target_type = target_type
        self.target_identifier = target_identifier
        self.rules = notification.rules

    def get_participants(self) -> Mapping[ExternalProviders, Iterable[Team | User]]:
        return get_send_to(
            project=self.project,
            target_type=self.target_type,
            target_identifier=self.target_identifier,
            event=self.event,
        )

    def get_subject(self, context: Mapping[str, Any] | None = None) -> str:
        return str(self.event.get_email_subject())

    @property
    def reference(self) -> Model | None:
        return self.group

    def get_recipient_context(
        self, recipient: Team | User, extra_context: Mapping[str, Any]
    ) -> MutableMapping[str, Any]:
        timezone = pytz.timezone("UTC")

        if isinstance(recipient, User):
            user_tz = UserOption.objects.get_value(user=recipient, key="timezone", default="UTC")
            try:
                timezone = pytz.timezone(user_tz)
            except pytz.UnknownTimeZoneError:
                pass
        return {
            **super().get_recipient_context(recipient, extra_context),
            "timezone": timezone,
        }

    def get_context(self) -> MutableMapping[str, Any]:
        environment = self.event.get_tag("environment")
        enhanced_privacy = self.organization.flags.enhanced_privacy
        rule_details = get_rules(self.rules, self.organization, self.project)
        context = {
            "project_label": self.project.get_full_name(),
            "group": self.group,
            "event": self.event,
            "link": get_group_settings_link(self.group, environment, rule_details),
            "rules": rule_details,
            "has_integrations": has_integrations(self.organization, self.project),
            "enhanced_privacy": enhanced_privacy,
            "commits": get_commits(self.project, self.event),
            "environment": environment,
            "slack_link": get_integration_link(self.organization, "slack"),
            "has_alert_integration": has_alert_integration(self.project),
        }

        # if the organization has enabled enhanced privacy controls we don't send
        # data which may show PII or source code
        if not enhanced_privacy:
            context.update({"tags": self.event.tags, "interfaces": get_interface_list(self.event)})

        return context

    def get_notification_title(self, context: Mapping[str, Any] | None = None) -> str:
        from sentry.integrations.slack.message_builder.issues import build_rule_url

        title_str = "Alert triggered"

        if self.rules:
            rule_url = build_rule_url(self.rules[0], self.group, self.project)
            title_str += f" <{rule_url}|{self.rules[0].label}>"

            if len(self.rules) > 1:
                title_str += f" (+{len(self.rules) - 1} other)"

        return title_str

    def send(self) -> None:
        from sentry.notifications.notify import notify

        metrics.incr("mail_adapter.notify")
        logger.info(
            "mail.adapter.notify",
            extra={
                "target_type": self.target_type.value,
                "target_identifier": self.target_identifier,
                "group": self.group.id,
                "project_id": self.project.id,
            },
        )

        participants_by_provider = self.get_participants()
        if not participants_by_provider:
            logger.info(
                "notifications.notification.rules.alertrulenotification.skip.no_participants",
                extra={
                    "target_type": self.target_type.value,
                    "target_identifier": self.target_identifier,
                    "group": self.group.id,
                    "project_id": self.project.id,
                },
            )
            return

        # Only calculate shared context once.
        shared_context = self.get_context()

        for provider, participants in participants_by_provider.items():
            notify(provider, self, participants, shared_context)

    def get_log_params(self, recipient: Team | User) -> Mapping[str, Any]:
        return {
            "target_type": self.target_type,
            "target_identifier": self.target_identifier,
            **super().get_log_params(recipient),
        }


class CommitData(TypedDict):
    author: User
    subject: str
    key: str


class ActiveReleaseAlertNotification(AlertRuleNotification):
    message_builder = "ActiveReleaseIssueNotificationMessageBuilder"
    metrics_key = "release_issue_alert"
    notification_setting_type = NotificationSettingTypes.ISSUE_ALERTS
    template_path = "sentry/emails/release_alert"

    def __init__(
        self,
        notification: Notification,
        target_type: ActionTargetType,
        target_identifier: int | None = None,
        last_release: Optional[Release] = None,
    ) -> None:
        from sentry.rules.conditions.active_release import ActiveReleaseEventCondition

        super().__init__(notification, target_type, target_identifier)
        self.last_release = (
            last_release
            if last_release
            else ActiveReleaseEventCondition.latest_release(notification.event)
        )

    def get_notification_title(self, context: Mapping[str, Any] | None = None) -> str:
        from sentry.integrations.slack.message_builder.issues import build_rule_url

        title_str = "Active Release alert triggered"

        if self.rules:
            rule_url = build_rule_url(self.rules[0], self.group, self.project)
            title_str += f" <{rule_url}|{self.rules[0].label}>"

            if len(self.rules) > 1:
                title_str += f" (+{len(self.rules) - 1} other)"

        return title_str

    def get_context(self) -> MutableMapping[str, Any]:
        environment = self.event.get_tag("environment")
        enhanced_privacy = self.organization.flags.enhanced_privacy
        rule_details = get_rules(self.rules, self.organization, self.project)
        context = {
            "project_label": self.project.get_full_name(),
            "group": self.group,
            "event": self.event,
            "link": get_group_settings_link(
                self.group, environment, rule_details, referrer="alert_email_release"
            ),
            "rules": rule_details,
            "has_integrations": has_integrations(self.organization, self.project),
            "enhanced_privacy": enhanced_privacy,
            "last_release": self.last_release,
            "last_release_link": self.release_url(self.last_release),
            "commits": self.get_release_commits(self.last_release),
            "environment": environment,
            "slack_link": get_integration_link(self.organization, "slack"),
            "has_alert_integration": has_alert_integration(self.project),
        }

        # if the organization has enabled enhanced privacy controls we don't send
        # data which may show PII or source code
        if not enhanced_privacy:
            context.update({"tags": self.event.tags, "interfaces": get_interface_list(self.event)})

        return context

    def get_release_commits(self, release: Release) -> Sequence[CommitData]:
        if not release:
            return []

        release_commits = (
            ReleaseCommit.objects.filter(release_id=release.id)
            .select_related("commit", "commit__author")
            .order_by("-order")
        )

        return [
            {
                "author": rc.commit.author,
                "subject": rc.commit.message.split("\n", 1)[0]
                if rc.commit.message
                else "no subject",
                "key": rc.commit.key,
            }
            for rc in release_commits
        ]

    def release_url(self, release: Release) -> str:
        params = {"project": release.project_id, "referrer": "alert_email_release"}
        url = "/organizations/{org}/releases/{version}/{params}".format(
            org=release.organization.slug,
            version=release.version,
            params="?" + urlencode(params),
        )

        return str(absolute_uri(url))
