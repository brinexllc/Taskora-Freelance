"""Correlated aggregates avoid rating/contract joins multiplying each other."""
from django.db.models import Avg, Count, F, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from .models import Contract, Profile, Review


def with_profile_metrics(queryset):
    reviews = Review.objects.filter(target_id=OuterRef('user_id'), published=True).order_by().values('target_id')
    completed = Contract.objects.filter(freelancer_id=OuterRef('user_id'), status=Contract.Status.COMPLETED).order_by().values('freelancer_id')
    # An accepted immutable submission is the evidence; settlement date is irrelevant.
    eligible = completed.filter(accepted_deliverable__isnull=False,
        accepted_deliverable__deadline_snapshot__isnull=False,
        accepted_deliverable__contract_id=F('pk'), dispute__isnull=True)

    def count(qs):
        return Coalesce(Subquery(qs.annotate(n=Count('pk')).values('n')[:1], output_field=IntegerField()), Value(0))

    return queryset.annotate(
        average_rating=Subquery(reviews.annotate(r=Avg('rating')).values('r')[:1]),
        metric_review_count=count(reviews), metric_completed_count=count(completed.filter(dispute__isnull=True)),
        metric_disputed_count=count(completed.filter(dispute__isnull=False)),
        metric_timely_total=count(eligible),
        metric_timely_count=count(eligible.filter(accepted_deliverable__created_at__lte=F('accepted_deliverable__deadline_snapshot'))),
    )


def metrics_for(profile):
    if hasattr(profile, 'metric_timely_total'):
        return profile
    if not hasattr(profile, '_loaded_metrics'):
        profile._loaded_metrics = with_profile_metrics(Profile.objects.filter(pk=profile.pk)).first()
    return profile._loaded_metrics
