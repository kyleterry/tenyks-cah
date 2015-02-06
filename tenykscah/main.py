import datetime
import random

from tenyksservice import TenyksService, run_service, FilterChain
from tenyksservice.config import settings

HELP_TEXT = '''Tenyks Cards Against Humanity
    Assuming the bot nick is `tenyks`:


    NEW PHASE:
        To create a new game:
            "tenyks: new game of cah"
            Shorthand version: "tenyks: new cah"

        Once a new game has been created, players will need to optin:
            "I'm in for cah"

        Once enough players have joined, the game host can start the game:
            "tenyks: start cah game"

    PLAY PHASE:
        Tenyks will inform you that you are the next one to throw down a question card.
        You can do this by saying the following:
            "tenyks: play card"

        Once a question card has been played, tenyks will send private messages to everyone
        who has opted in. This message will include a numbered hand of cards.
        Once you have decided what card you want to play, you send a private message to tenyks:
            "play 3"

        When everyone has chosen a card to play, tenyks will inform the channel that everyone is all in.
        The person playing the question card will then tell tenyks to read the cards:
            "tenyks: read cards"

        Tenyks will read all the cards people are playing into the channel. They will be indexed.
        The question card player can then choose a number when they pick who won the round:
            "tenyks: 4 wins"

        Tenyks will then let the channel know who had card number 4. Then the next person in the player
        rotation is up and the game starts back at the beginning of PLAY PHASE.

    Canceling the game:
        You can tell tenyks to cancel the current game only if you are the game host:
            "tenyks: cancel cah game"
'''

GAME_DURATION = 36000 # in seconds

CARD_TYPE_QUESTION = 'question'
CARD_TYPE_ANSWER = 'answer'

GAME_PHASE_NEW = 0
GAME_PHASE_QUESTION = 1
GAME_PHASE_ANSWERS = 2
GAME_PHASE_SELECTION = 3
GAME_PHASE_CONCLUSION = 4

MIN_PLAYERS = 3


class CardsAgainstHumanityService(TenyksService):
    irc_message_filters = {
        'new_game': FilterChain(
            [r'^new game of cah$', r'^new cah$'],
            direct_only=True),

        'start_game': FilterChain(
            [r'^start cah game$'],
            direct_only=True),

        'cancel_game': FilterChain(
            [r'^cancel cah game$'],
            direct_only=True),

        'join_game': FilterChain(
            [r'^I\'m in for cah', r'^I\'ll play$'],
            direct_only=False),

        'play_question_card': FilterChain(
            [r'^play card$'],
            direct_only=True),

        'play_answer_card': FilterChain(
            [r'^play (?P<cardnum>[0-9]*)$'],
            private_only=True),

        'read_cards': FilterChain(
            [r'^read cards$'],
            direct_only=True),

        'choose_card': FilterChain(
            [r'^(?P<cardnum>[0-9]*) wins$'],
            direct_only=True),
    }

    help_text = HELP_TEXT

    def __init__(self, *args, **kwargs):
        # keys are IRC channel names and values are game objects
        self.games = {}
        super(CardsAgainstHumanityService, self).__init__(*args, **kwargs)

    def handle_new_game(self, data, match):
        channel = data['from_channel']
        nick = data['nick']
        if channel in self.games and not self.games[channel].is_expired():
            self.send('{}: You already have a game started. Use `tenyks: cah status` to get more info.'.format(nick), data)
            return
        self.games[channel] = CardsAgainstHumanity(channel)
        self.games[channel].new_player(nick, host=True)
        self.send('{} has started a new game of cards against humanity. Please let me know if you want to play by saying "I\'m in for cah".'.format(nick), data)
        self.send('Games are good for 10 hours. After that, asking me to start a new game will succeed if an old one isn\'t complete', data)
        self.send('The game host is the one who created the new game.', data)
        self.send('Only the game host can cancel games. One can do that by asking me: "tenyks: cancel cah game".', data)

    def handle_join_game(self, data, match):
        channel = data['from_channel']
        nick = data['nick']
        if channel not in self.games:
            self.send('No one has created a new game yet!', data)
            return

        game = self.games[channel]
        if game.current_phase > GAME_PHASE_NEW:
            self.send('{}: You are too late. The game has already started.'.format(nick), data)
        if game.player_exists(nick):
            self.send('{}: You already joined the game'.format(nick), data)
            return
        game.new_player(nick)
        self.send('{}: You have joined the game. It should start shortly. I will send you a PM with your hand of cards.'.format(nick), data)

    def handle_start_game(self, data, match):
        channel = data['from_channel']
        nick = data['nick']
        if channel not in self.games:
            self.send('No one has created a new game yet!', data)
            return

        game = self.games[channel]

        if game.current_phase > GAME_PHASE_NEW:
            self.send('{}: The game has already started.'.format(nick), data)

        if game.player_count() < MIN_PLAYERS:
            self.send('{}, the minimum amount of players is {} and you currently have {} so I cannot start the game.'.format(nick, MIN_PLAYERS, game.player_count()), data)
            return

        game.initial_deal()

        game.current_phase = GAME_PHASE_QUESTION

        player = game.set_and_return_next_player(init=True)
        self.send('{}, you\'re up. Say "play card" in the channel to throw down your question card'.format(player.name), data)

    def handle_cancel_game(self, data, match):
        channel = data['from_channel']
        nick = data['nick']
        if channel not in self.games:
            self.send('No one has created a new game yet!', data)
            return

        game = self.games[channel]

        if game.player_exists(nick):
            player = game.get_player(nick)
            if player and player.host:
                del self.games[channel]
                self.send('The game was canceled :(', data)

    def handle_play_question_card(self, data, match):
        channel = data['from_channel']
        nick = data['nick']
        if channel not in self.games:
            self.send('No one has created a new game yet!', data)
            return

        game = self.games[channel]

        if game.current_phase == GAME_PHASE_QUESTION:
            if game.current_question_player().name != nick:
                data['target'] = nick
                self.send('Hold your horses. A question card needs to be played first.', data)
                return
            card = game.play_question_card()
            self.send('Alright, here we go:', data)
            self.send(card.text, data)

            self._pm_hands(data, game)

    def handle_play_answer_card(self, data, match):
        nick = data['nick']

        # This is a really dirty hack that leads to people only being able to
        # play one game at a time even if they are in different channels
        for channel in self.games:
            game = self.games[channel]
            if game.get_player(nick):
                break
            game = None

        if not game:
            self.send('No one has created a new game yet!', data)
            return

        if game.current_phase == GAME_PHASE_QUESTION:
            data['target'] = nick
            if game.current_question_player().name != nick:
                self.send('Hold your horses. A question card needs to be played first.', data)
                return
            elif game.current_question_player().name == nick:
                self.send('Nice try.', data)
                return

        number = int(match.groupdict()['cardnum'])


        player = game.get_player(nick)
        if number > len(player.hand):
            self.send('You can\'t play {} as it doesn\'t exist.'.format(number))
            return

        game.play_answer_card(player, number)

        if len(game.round_answer_cards) == (len(game.players) - 1):
            game.current_phase = GAME_PHASE_SELECTION
            data['target'] = game.channel
            self.send('Okay, everyone is in with their answers.', data)
            self.send('{}: you can say "read cards" now to have me list them.'.format(game.current_question_player().name), data)

    def handle_read_cards(self, data, match):
        channel = data['from_channel']
        nick = data['nick']
        if channel not in self.games:
            self.send('No one has created a new game yet!', data)
            return

        game = self.games[channel]

        if game.current_phase != GAME_PHASE_SELECTION:
            self.send('{}: Not everyone is all in yet. Maybe nudge them?'.format(nick), data)
            return

        if nick != game.current_question_player().name:
            return

        random.shuffle(game.round_answer_cards)
        for i, card in enumerate(game.round_answer_cards):
            self.send('{} - {}'.format(i, card.text), data)

    def handle_choose_card(self, data, match):
        channel = data['from_channel']
        nick = data['nick']
        if channel not in self.games:
            self.send('No one has created a new game yet!', data)
            return

        game = self.games[channel]

        if game.current_phase != GAME_PHASE_SELECTION:
            self.send('{}: You can\'t choose a card if I haven\'t even read them yet...'.format(nick), data)
            return

        if nick != game.current_question_player().name:
            return

        number = int(match.groupdict()['cardnum'])

        if number > len(game.round_answer_cards):
            self.send('{}: what the fuck, dude...'.format(nick), data)
            return

        card = game.round_answer_cards[number]
        player = game.choose_card_as_winner(card)

        self.send('{}: you won the round! HOLY SHIT YOU WON THE ROUND!'.format(player.name), data)

        game.replenish()
        game.current_phase = GAME_PHASE_QUESTION

        player = game.set_and_return_next_player()
        self.send('{}, you\'re up. Say "play card" in the channel to throw down your question card'.format(player.name), data)

    def _pm_hands(self, data, game):
        qp = game.players[game.player_index]
        for player in game.players:
            if player.name != qp.name:
                player_data = data
                player_data['target'] = player.name
                self.send('Here\'s your hand:', player_data)
                self.send(' ', player_data)

                for i, card in enumerate(player.hand):
                    self.send('{} - {}'.format(i, card.text), player_data)

                self.send(' ', player_data)
                self.send('Please choose a card and let me know what number you\'d like to play.', player_data)


class CardsAgainstHumanity(object):

    def __init__(self, channel):
        self.channel = channel
        self.created = datetime.datetime.now()
        self.current_phase = GAME_PHASE_NEW
        self.players = []
        self.all_answer_cards = []
        self.all_question_cards = []
        self.round_number = 0
        self.round_answer_cards = []
        self.player_index = 0
        with open('./answers.txt', 'r') as f:
            [self.all_answer_cards.append(Card(CARD_TYPE_ANSWER, line)) for line in f]
        random.shuffle(self.all_answer_cards)
        with open('./questions.txt', 'r') as f:
            [self.all_question_cards.append(Card(CARD_TYPE_QUESTION, line)) for line in f]
        random.shuffle(self.all_question_cards)

    def initial_deal(self):
        if self.current_phase > GAME_PHASE_NEW:
            return

        iterations = len(self.players) * 5

        j = 0
        for i in range(iterations):
            card = self.all_answer_cards.pop()
            try:
                player = self.players[j]
            except IndexError:
                j = 0
                player = self.players[j]

            player.hand.append(card)
            j += 1

    def replenish(self):
        if self.current_phase == GAME_PHASE_SELECTION:
            for player in self.players:
                if player.name != self.current_question_player().name:
                    player.hand.append(self.all_answer_cards.pop())

    def new_player(self, name, host=False):
        if self.player_exists(name):
            return

        player = Player(name)
        player.host = True
        self.players.append(player)

    def player_exists(self, name):
        for player in self.players:
            if player.name == name:
                return True
        return False

    def player_count(self):
        return len(self.players)

    def set_and_return_next_player(self, init=False):
        if init:
            self.player_index = 0
        else:
            self.player_index += 1
            if self.player_index + 1 > len(self.players):
                self.player_index = 0

        player = self.players[self.player_index]
        return player

    def get_player(self, name):
        for player in self.players:
            if name == player.name:
                return player

    def current_question_player(self):
        return self.players[self.player_index]

    def play_question_card(self):
        player = self.current_question_player()
        card = self.all_question_cards.pop()
        player.current_question_card = card
        player.question_cards.append(card)

        # reset shit
        self.current_phase = GAME_PHASE_ANSWERS
        self.round_number += 1
        self.round_answer_cards = []

        return card

    def play_answer_card(self, player, index):
        card = player.hand.pop(index)
        player.answer_cards.append(card)
        self.round_answer_cards.append(card)
        card.round = self.round_number

    def choose_card_as_winner(self, card):
        card.winner = True
        for player in self.players:
            for _card in player.answer_cards:
                if card.text == _card.text:
                    return player

    def is_expired(self):
        now = datetime.datetime.now()
        td = now - self.created
        if td.seconds > GAME_DURATION:
            return True
        return False


class Card(object):

    def __init__(self, card_type, text):
        self.card_type = card_type
        self.text = text
        self.round = None
        self.winner = False

    def is_spent(self):
        if self.round is None:
            return False
        return True


class Player(object):

    def __init__(self, name):
        self.name = name
        self.answer_cards = []
        self.question_cards = []
        self.current_question_card = None
        self.host = True
        self.hand = []


def main():
    run_service(CardsAgainstHumanityService)

if __name__ == '__main__':
    main()
