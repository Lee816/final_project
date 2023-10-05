from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import redirect, get_object_or_404
from django.views import View
from django.views.generic import (
    ListView,
    DetailView,
    DeleteView,
    FormView,
)

from common.utils import Tags, s3_file_upload, InfiniteListView
from manager.models import Study, File
from recruit.forms import SearchForm, ApplicationForm, RecruitForm
from recruit.models import Recruit, Register


# Create your views here.
class RecruitView(InfiniteListView):
    model = Recruit
    template_name = "recruits/index.html"
    context_object_name = "recruits"
    paginate_by = 10

    def get_queryset(self):
        queryset = Recruit.objects.all()
        query = self.request.GET.get("query")
        tag = self.request.GET.get("tag")

        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(process__icontains=query)
                | Q(info__icontains=query)
                | Q(target__icontains=query)
            ).distinct()
        if tag:
            queryset = queryset.filter(tags__name__icontains=tag)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tag"] = self.request.GET.get("tag")
        context["form"] = SearchForm()
        if self.request.user.is_authenticated:
            context["in_studies"] = Recruit.objects.filter(
                study__members=self.request.user
            )
            context["liked_studies"] = Recruit.objects.filter(
                like_users=self.request.user
            )
        else:
            context["in_studies"] = None
            context["liked_studies"] = None
        return context


@login_required
def like_recruit(request, pk):
    recruit = get_object_or_404(Recruit, pk=pk)
    if request.user.is_authenticated:
        recruit.like_users.add(request.user)
    return redirect("recruits:index")


@login_required()
def unlike_recruit(request, pk):
    recruit = get_object_or_404(Recruit, pk=pk)
    if request.user.is_authenticated:
        recruit.like_users.remove(request.user)
    return redirect("recruits:index")


class RecruitDetailView(DetailView):
    model = Recruit
    template_name = "recruits/detail.html"
    context_object_name = "recruit"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = ApplicationForm()
        return context

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("users:login")

        form = ApplicationForm(request.POST)
        recruit = self.get_object()
        if Register.objects.filter(recruit=recruit, requester=request.user).exists():
            messages.error(request, "이미 신청하셨습니다.")
            return redirect("recruits:recruit_detail", recruit.id)
        if form.is_valid():
            register = form.save(commit=False)
            register.recruit = self.get_object()
            register.requester = request.user
            register.save()
            return redirect("recruits:index")
        else:
            return self.render_to_response(self.get_context_data(form=form))


class RequestView(LoginRequiredMixin, ListView):
    model = Register
    template_name = "recruits/requests.html"
    context_object_name = "registers"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(recruit__creator=self.request.user, is_joined=None)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


class ConfirmRegisterView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        register = Register.objects.get(pk=kwargs["pk"])
        register.is_joined = True
        register.save()
        recruit = register.recruit
        recruit.members.add(register.requester)
        recruit.save()
        study = recruit.study
        study.members.add(register.requester)
        study.save()
        return redirect(
            reverse_lazy("recruits:recruit_request", args=[register.recruit.id])
        )


class CancelRegisterView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        register = Register.objects.get(pk=kwargs["pk"])
        register.is_joined = False
        register.save()
        return redirect(
            reverse_lazy("recruits:recruit_request", args=[register.recruit.id])
        )


class RecruitCreateView(LoginRequiredMixin, FormView):
    form_class = RecruitForm
    context_object_name = "recruit"
    template_name = "recruits/recruit_form.html"
    view_type = "create"

    def form_valid(self, form):
        form.instance.creator = self.request.user
        start_date = form.cleaned_data.get("start")
        end_date = form.cleaned_data.get("end")
        deadline = form.cleaned_data.get("deadline")
        tags = form.cleaned_data.get("tags")

        if end_date and start_date and end_date <= start_date:
            form.add_error("end", "End date should be after the start date.")
            return self.form_invalid(form)

        if deadline and start_date and deadline > start_date:
            form.add_error(
                "deadline", "Deadline should be on or before the start date."
            )
            return self.form_invalid(form)

        if len(tags) > 3:
            form.add_error("tags", "You can only select up to 3 tags.")
            return self.form_invalid(form)
        tag_list = Tags()
        for tag in tags:
            if tag not in tag_list:
                form.add_error("tags", f"{tag} is not a valid tag.")
                return self.form_invalid(form)

        study = Study.objects.create(
            creator=self.request.user,
            title=form.cleaned_data["title"],
            start=form.cleaned_data["start"],
            end=form.cleaned_data["end"],
            process=form.cleaned_data["process"],
            info=form.cleaned_data["info"],
        )

        study.members.add(self.request.user)

        instance = form.save(commit=False)
        instance.study = study
        instance.save()

        instance.members.add(self.request.user)

        for tag in form.cleaned_data["tags"]:
            instance.tags.add(tag)

        for file in self.request.FILES.getlist("file"):
            name, url = s3_file_upload(file, "files")
            file_instance = File(url=url, name=name)
            file_instance.save()
            instance.files.add(file_instance)

        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("recruits:index")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tags"] = list(Tags())
        return context


from django.urls import reverse_lazy
from django.views.generic.edit import UpdateView


class RecruitModifyView(LoginRequiredMixin, UpdateView):
    model = Recruit
    form_class = RecruitForm
    template_name = "recruits/recruit_form.html"
    context_object_name = "recruit"

    def get_success_url(self):
        return reverse_lazy("recruits:index")

    def form_valid(self, form):
        start_date = form.cleaned_data.get("start")
        end_date = form.cleaned_data.get("end")
        deadline = form.cleaned_data.get("deadline")
        tags = form.cleaned_data.get("tags")

        if end_date and start_date and end_date <= start_date:
            form.add_error("end", "End date should be after the start date.")
            return self.form_invalid(form)

        if deadline and start_date and deadline > start_date:
            form.add_error(
                "deadline", "Deadline should be on or before the start date."
            )
            return self.form_invalid(form)

        if len(tags) > 3:
            form.add_error("tags", "You can only select up to 3 tags.")
            return self.form_invalid(form)

        tag_list = Tags()

        for tag in tags:
            if tag not in tag_list:
                form.add_error("tags", f"{tag} is not a valid tag.")
                return self.form_invalid(form)

        instance = self.object

        for file in self.request.FILES.getlist("file"):
            name, url = s3_file_upload(file, "files")
            file_instance = File(url=url, name=name)
            file_instance.save()
            instance.files.add(file_instance)

        instance.save()

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tags"] = list(Tags())
        return context


class RecruitDeleteView(LoginRequiredMixin, DeleteView):
    model = Recruit
    template_name = "recruits/recruit_confirm_delete.html"

    def get_success_url(self):
        return reverse_lazy("recruits:index")


class FileDeleteView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        file = get_object_or_404(File, pk=kwargs["file_pk"])
        recruit = get_object_or_404(Recruit, pk=kwargs["recruit_pk"])
        file.recruits.remove(recruit)  # Remove the association with the recruit.
        if not file.recruits.exists():  # If there are no more associated recruits...
            file.delete()  # ...then delete the file.
        return redirect("recruits:modify_recruit", pk=recruit.id)
