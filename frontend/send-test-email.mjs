import { Resend } from 'resend';

const apiKey = process.env.RESEND_API_KEY;

if (!apiKey) {
  throw new Error('Не задана переменная RESEND_API_KEY');
}

const resend = new Resend(apiKey);

try {
  const { data, error } = await resend.emails.send({
    from: 'Taskora <onboarding@resend.dev>',
    to: ['brinexmchj@gmail.com'],
    subject: 'Проверка отправки писем Taskora',
    html: '<p>Отправка писем через <strong>Resend</strong> работает!</p>',
  });

  if (error) {
    console.error('Ошибка отправки:', error);
    process.exitCode = 1;
  } else {
    console.log('Письмо принято к отправке. ID:', data.id);
  }
} catch (error) {
  console.error('Ошибка запроса:', error.message);
  process.exitCode = 1;
}