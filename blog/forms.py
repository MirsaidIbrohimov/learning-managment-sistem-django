import re

from django import forms

from .models import Post, PostComment


class PostForm(forms.ModelForm):
    title = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Post sarlavhasi'})
    )
    content = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Post matni...', 'rows': 6})
    )
    image = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )
    post_type = forms.ChoiceField(
        choices=Post.POST_TYPES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    is_published = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = Post
        fields = ['title', 'content', 'image', 'post_type', 'is_published']


class CommentForm(forms.ModelForm):
    content = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Izoh yozing...',
            'rows': 3,
            'maxlength': 1000,
        })
    )

    class Meta:
        model = PostComment
        fields = ['content']

    def clean_content(self):
        content = ' '.join(self.cleaned_data['content'].split())
        words = re.findall(r"[^\W\d_]+(?:['ʻ’][^\W\d_]+)*", content, re.UNICODE)
        letters = ''.join(char for word in words for char in word if char.isalpha()).lower()
        vowels = set('aeiouаеёиоуыэюя')

        meaningful_words = 0
        for word in words:
            normalized_word = word.lower()
            has_vowel = any(char in vowels for char in normalized_word)
            has_consonant = any(char.isalpha() and char not in vowels for char in normalized_word)
            if len(normalized_word.replace("'", '').replace('ʻ', '').replace('’', '')) >= 3 and has_vowel and has_consonant:
                meaningful_words += 1

        if len(letters) < 10 or len(words) < 2 or meaningful_words < 2:
            raise forms.ValidationError(
                "Iltimos, kamida ikki tuşunarli sözdan iborat mazmunli izoh yozing."
            )

        if len(set(letters)) < 4 or re.search(r'(.)\1{3,}', letters):
            raise forms.ValidationError(
                "Izohda takroriy yoki tasodifiy belgilar köp. Fikringizni tuşunarli yozing."
            )

        return content
