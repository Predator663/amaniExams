from rest_framework import serializers, viewsets

from accounts.permissions import IsAdminRole, IsAnyUser, IsStaffUser
from core.models import audit
from .models import AcademicYear, SchoolClass, Subject, Term, TeacherAssignment


class SchoolClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolClass
        fields = ["id", "name", "form_level", "stream"]


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "name", "code", "language", "practice_enabled"]


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherAssignment
        fields = ["id", "teacher", "subject", "school_class"]


class AdminWriteStaffRead(viewsets.ModelViewSet):
    """Staff may read; only admins may change (ADM-03, ADM-04)."""

    read_permission = IsStaffUser

    def get_permissions(self):
        cls = self.read_permission if self.request.method in ("GET", "HEAD", "OPTIONS") else IsAdminRole
        return [p() for p in self.permission_classes] + [cls()]

    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request.user, f"{self.basename}.create", obj.pk)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request.user, f"{self.basename}.edit", obj.pk)

    def perform_destroy(self, instance):
        audit(self.request.user, f"{self.basename}.delete", instance.pk)
        instance.delete()


class SchoolClassViewSet(AdminWriteStaffRead):
    queryset = SchoolClass.objects.all()
    serializer_class = SchoolClassSerializer


class SubjectViewSet(AdminWriteStaffRead):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer


class AssignmentViewSet(AdminWriteStaffRead):
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        qs = TeacherAssignment.objects.all()
        u = self.request.user
        return qs if u.is_admin_role else qs.filter(teacher=u)


class YearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = ["id", "name", "is_current"]


class TermSerializer(serializers.ModelSerializer):
    year_name = serializers.CharField(source="year.name", read_only=True)

    class Meta:
        model = Term
        fields = ["id", "year", "year_name", "name", "start_date", "end_date"]

    def validate(self, d):
        s, e = d.get("start_date", getattr(self.instance, "start_date", None)), d.get("end_date", getattr(self.instance, "end_date", None))
        if s and e and e < s:
            raise serializers.ValidationError({"end_date": "The end date must be after the start date."})
        return d


class AcademicYearViewSet(AdminWriteStaffRead):
    """Every logged-in user may read years and terms (students need them for report cards)."""

    queryset = AcademicYear.objects.all()
    serializer_class = YearSerializer
    read_permission = IsAnyUser

    def _one_current(self, obj):
        if obj.is_current:
            AcademicYear.objects.exclude(pk=obj.pk).update(is_current=False)

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._one_current(serializer.instance)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._one_current(serializer.instance)


class TermViewSet(AdminWriteStaffRead):
    serializer_class = TermSerializer
    read_permission = IsAnyUser

    def get_queryset(self):
        qs = Term.objects.select_related("year")
        if self.request.query_params.get("year"):
            qs = qs.filter(year_id=self.request.query_params["year"])
        return qs
