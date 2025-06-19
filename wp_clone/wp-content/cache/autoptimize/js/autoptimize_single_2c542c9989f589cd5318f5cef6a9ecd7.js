jQuery(function($){'use strict';function rot13(s){return s.replace(/[a-zA-Z]/g,function(c){return String.fromCharCode((c<='Z'?90:122)>=(c=c.charCodeAt(0)+13)?c:c-26);});}
function fetchEmail(el){var email=el.getAttribute('data-enc-email');if(!email){return null;}
email=email.replace(/\[at\]/g,'@');email=rot13(email);return email;}
function parseTitle(el){var title=el.getAttribute('title');var email=fetchEmail(el);if(title&&email){title=title.replace('{{email}}',email);el.setAttribute('title',title);}}
function setInputValue(el){var email=fetchEmail(el);if(email){el.setAttribute('value',email);}}
function mailto(el){var email=fetchEmail(el);if(email){window.location.href='mailto:'+email;}}
function revert(el,rtl){var email=fetchEmail(el);if(email){rtl.text(email);rtl.removeClass('eeb-rtl');}}
document.addEventListener('copy',function(e){$('a[data-enc-email]').each(function(){var rtl=$(this).find('.eeb-rtl');if(rtl.text()){revert(this,rtl);}});console.log('copy');});$('body').on('click','a[data-enc-email]',function(){mailto(this);});$('a[data-enc-email]').each(function(){parseTitle(this);});$('input[data-enc-email]').each(function(){setInputValue(this);});});