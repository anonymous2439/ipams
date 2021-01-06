from django import forms
from records.models import Record, Publication, Conference, Author, Collaboration, Budget, AuthorRole, PublicationLevel, \
    Classification, PSCEDClassification, CheckedRecord, RecordUpload

ASSESSMENT_CHOICES = (('pending', 'pending'), ('approved', 'approved'), ('declined', 'declined'))


class RecordForm(forms.ModelForm):
    use_required_attribute = False

    class Meta:
        model = Record
        fields = ('title', 'year_accomplished', 'abstract', 'classification', 'psced_classification', 'abstract_file', 'record_type')

    def save(self, commit=True):
        title = self.cleaned_data.get('title')
        year_accomplished = self.cleaned_data.get('year_accomplished')
        classification = self.cleaned_data.get('classification')
        psced_classification = self.cleaned_data.get('psced_classification')
        abstract = self.cleaned_data.get('abstract', None)
        record_len = len(Record.objects.filter(title=title, year_accomplished=year_accomplished, abstract=abstract,
                                               classification=classification,
                                               psced_classification=psced_classification))
        if record_len == 0 or abstract is not None:
            m = super(RecordForm, self).save(commit=False)
            if commit:
                m.save()
            return m
        return None


class PublicationForm(forms.ModelForm):
    use_required_attribute = False
    publication_name = forms.CharField(required=False)

    class Meta:
        model = Publication
        fields = ('isbn', 'issn', 'isi', 'year_published', 'publication_level',)

    def save(self, commit=True):
        m = super(PublicationForm, self).save(commit=False)
        m.name = self.cleaned_data.get('publication_name')
        if commit:
            m.save()
        return m


class AuthorForm(forms.ModelForm):
    use_required_attribute = False

    class Meta:
        model = Author
        fields = ('name', 'author_role')


class BudgetForm(forms.ModelForm):
    use_required_attribute = False

    class Meta:
        model = Budget
        fields = ('budget_allocation', 'funding_source', 'budget_type')


class ConferenceForm(forms.ModelForm):
    use_required_attribute = False

    class Meta:
        model = Conference
        fields = ('title', 'date', 'venue', 'conference_level')


class CollaborationForm(forms.ModelForm):
    use_required_attribute = False

    class Meta:
        model = Collaboration
        fields = ('industry', 'institution', 'collaboration_type')


class CheckedRecordForm(forms.ModelForm):
    use_required_attribute = False

    class Meta:
        model = CheckedRecord
        fields = ('comment',)


class AssessmentForm(forms.Form):
    comment = forms.CharField(required=False, label='COMMENTS / RECOMMENDATIONS', widget=forms.Textarea)
