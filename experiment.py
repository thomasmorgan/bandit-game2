""" The Bandit Game! """

from wallace.experiments import Experiment
from wallace.nodes import Agent, Source
from wallace.models import Info, Network, Vector
from wallace.networks import DiscreteGenerational
from wallace.information import Gene
from psiturk.models import Participant
import random
from json import dumps
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql.expression import cast
from sqlalchemy import Integer
from flask import Blueprint, Response, request, render_template
import os
from psiturk.psiturk_config import PsiturkConfig
import requests
from wallace import db
config = PsiturkConfig()


class BanditGame(Experiment):

    def __init__(self, session):
        super(BanditGame, self).__init__(session)

        """ Wallace parameters """
        self.task = "The Bandit Game"
        self.verbose = True
        self.experiment_repeats = 1
        self.practice_repeats = 0
        self.agent = BanditAgent
        self.generation_size = 40
        self.generations = 40
        self.network = lambda: BanditGenerational(generations=self.generations,
                                                  generation_size=self.generation_size,
                                                  initial_source=True)
        self.bonus_payment = 0.5
        self.initial_recruitment_size = self.generation_size
        self.instruction_pages = ["instructions/instruct-1.html",
                                  "instructions/instruct-2.html",
                                  "instructions/instruct-3.html",
                                  "instructions/instruct-4.html",
                                  "instructions/instruct-5.html"]
        self.debrief_pages = ["debriefing/debrief-1.html"]
        self.known_classes["Pull"] = Pull

        """ BanditGame parameters """
        # how many bandits each node visits
        self.n_trials = 20

        # how many bandits there are
        self.n_bandits = 4

        # how many arms each bandit has
        self.n_options = 10

        # how many times you can pull the arms
        self.n_pulls = 10

        # how much each unit of memory costs fitness
        self.memory_cost = 2

        # fitness affecting parameters
        self.f_min = 10
        self.f_scale_factor = 0.01
        self.f_power_factor = 2

        # genetic parameters
        self.allow_memory = True
        self.allow_curiosity = True
        self.seed_memory = 1
        self.seed_curiosity = 1

        if not self.networks():
            self.setup()
        self.save()

    def setup(self):
        super(BanditGame, self).setup()
        for net in self.networks():
            source = GeneticSource(network=net)
            source.create_genes()
            for bandit in range(self.n_bandits):
                b = Bandit(network=net)
                b.bandit_id = bandit
                b.num_tiles = self.n_options
                b.treasure_tile = int(random.random()*self.n_options) + 1

    def recruit(self):
        self.log("running recruit")
        participants = Participant.query.with_entities(Participant.status).all()

        # if all network are full close recruitment
        if not self.networks(full=False):
            self.log("all networks full, closing recruitment")
            self.recruiter().close_recruitment()
        # if a complete generation has finished and no-one is playing, recruit
        elif (len([p for p in participants if p.status == 101]) % self.generation_size == 0 and
              not [p for p in participants if p.status < 100]):
            self.log("generation finished, recruiting another")
            self.recruiter().recruit_participants(n=self.generation_size)
        else:
            self.log("generation not finished, not recruiting")

    def data_check(self, participant):

        # get the necessary data
        networks = Network.query.all()
        nodes = BanditAgent.query.filter_by(participant_id=participant.uniqueid).all()
        node_ids = [n.id for n in nodes]
        genes = Gene.query.filter(Gene.origin_id.in_(node_ids)).all()
        incoming_vectors = Vector.query.filter(Vector.destination_id.in_(node_ids)).all()
        outgoing_vectors = Vector.query.filter(Vector.origin_id.in_(node_ids)).all()
        decisions = Pull.query.filter(Pull.origin_id.in_(node_ids)).all()

        try:
            # 1 node per network
            for net in networks:
                assert len([n for n in nodes if n.network_id == net.id]) == 1

            # 1 curiosity and memory gene per node
            for node in nodes:
                assert len([g for g in genes if g.origin_id == node.id]) == 2
                assert len([g for g in genes if g.origin_id == node.id and g.type == "memory_gene"]) == 1
                assert len([g for g in genes if g.origin_id == node.id and g.type == "curiosity_gene"]) == 1

            # 1 vector (incoming) per node
            for node in nodes:
                assert len([v for v in outgoing_vectors if v.origin_id == node.id]) == 0
                assert len([v for v in incoming_vectors if v.destination_id == node.id]) == 1

            # n_trials decision per node
            for node in nodes:
                assert (len([d for d in decisions if d.origin_id == node.id and d.check == "false"])) == self.n_trials

            # 0 checks if remembered, otherwise "curiosity" checks
            for node in nodes:
                curiosity = int([g for g in genes if g.origin_id == node.id and g.type == "curiosity_gene"][0].contents)
                final_decisions = [d for d in decisions if d.origin_id == node.id and d.check == "false"]
                for decision in final_decisions:
                    if decision.remembered == "true":
                        assert (len([d for d in decisions if d.origin_id == node.id and d.check == "true" and d.bandit_id == decision.bandit_id and d.trial == decision.trial])) == 0
                    else:
                        assert (len([d for d in decisions if d.origin_id == node.id and d.check == "true" and d.bandit_id == decision.bandit_id and d.trial == decision.trial])) == curiosity

            # all decisions have an int payoff
            for d in decisions:
                if d.check == "false":
                    assert isinstance(int(d.contents), int)

            # all nodes have a fitness
            for node in nodes:
                assert isinstance(node.fitness, float)

            self.log("Data check passed")
            return True
        except:
            import traceback
            traceback.print_exc()
            return False

    def bonus(self, participant):
        total_score = 0

        # get the non-practice networks:
        networks = Network.query.all()
        networks_ids = [n.id for n in networks if n.role != "practice"]

        # query all nodes, bandits, pulls and Genes
        nodes = BanditAgent.query.filter_by(participant_id=participant.uniqueid).all()
        nodes = [n for n in nodes if n.network_id in networks_ids]
        bandits = Bandit.query.all()
        node_ids = [n.id for n in nodes]
        pulls = Pull.query.filter(Pull.origin_id.in_(node_ids)).all()
        curiosity_genes = CuriosityGene.query.filter(Gene.origin_id.in_(node_ids)).all()

        for node in nodes:
            # for every node get its curiosity and decisions
            curiosity = int([g for g in curiosity_genes if g.origin_id == node.id][0].contents)
            decisions = [p for p in pulls if p.origin_id == node.id and p.check == "false"]

            for decision in decisions:
                # for each decision, get the bandit and the right answer
                bandit = [b for b in bandits if b.network_id == node.network_id and b.bandit_id == decision.bandit_id][0]
                right_answer = bandit.treasure_tile

                # if they get it right score = potential score
                if right_answer == int(decision.contents):
                    score = self.n_pulls - curiosity
                else:
                    score = 0

                # save this info the the decision and update the running totals
                decision.payoff = score
                total_score += score

        total_trials = self.n_trials * self.experiment_repeats

        bonus = (total_score/(1.0*total_trials))/5.0

        bonus = max(min(bonus, 1.0), 0.0)*self.bonus_payment

        bonus = round(bonus, 2)

        return bonus

    def attention_check(self, participant):
        bandits = Bandit.query.all()
        nodes = BanditAgent.query.filter_by(participant_id=participant.uniqueid).all()
        pulls = []
        for node in nodes:
            pulls.extend(node.infos(type=Pull))

        final_decisions = [p for p in pulls if p.check == "false"]
        checks = [p for p in pulls if p.check == "true"]

        times_found_treasure = 0
        times_chose_treasure = 0

        for d in final_decisions:
            if d.remembered == "false":
                right_answer = [b for b in bandits if b.network_id == d.network_id and b.bandit_id == d.bandit_id][0].treasure_tile
                checked_tiles = [int(c.contents) for c in checks if c.network_id == d.network_id and c.trial == d.trial]
                if right_answer in checked_tiles:
                    times_found_treasure += 1
                    if int(d.contents) == right_answer:
                        times_chose_treasure += 1

        diff = times_found_treasure - times_chose_treasure

        return diff < 3


class BanditGenerational(DiscreteGenerational):

    __mapper_args__ = {"polymorphic_identity": "bandit_generational"}

    def add_node(self, node):
        super(BanditGenerational, self).add_node(newcomer=node)
        node.receive()


class GeneticSource(Source):
    """ A source that initializes the genes of the first generation """

    __mapper_args__ = {"polymorphic_identity": "genetic_source"}

    def _what(self):
        return Gene

    def create_genes(self):
        exp = BanditGame(db.session)
        if exp.allow_memory:
            MemoryGene(origin=self, contents=exp.seed_memory)
        else:
            MemoryGene(origin=self, contents=0)

        if exp.allow_curiosity:
            CuriosityGene(origin=self, contents=exp.seed_curiosity)
        else:
            CuriosityGene(origin=self, contents=1)


class Bandit(Source):
    """ a bandit that you can play with """

    __mapper_args__ = {"polymorphic_identity": "bandit"}

    @hybrid_property
    def num_tiles(self):
        return int(self.property1)

    @num_tiles.setter
    def num_tiles(self, num_tiles):
        self.property1 = repr(num_tiles)

    @num_tiles.expression
    def num_tiles(self):
        return cast(self.property1, Integer)

    @hybrid_property
    def treasure_tile(self):
        return int(self.property2)

    @treasure_tile.setter
    def treasure_tile(self, treasure_tile):
        self.property2 = repr(treasure_tile)

    @treasure_tile.expression
    def treasure_tile(self):
        return cast(self.property2, Integer)

    @hybrid_property
    def bandit_id(self):
        return int(self.property3)

    @bandit_id.setter
    def bandit_id(self, bandit_id):
        self.property3 = repr(bandit_id)

    @bandit_id.expression
    def bandit_id(self):
        return cast(self.property3, Integer)


class MemoryGene(Gene):
    """ A gene that controls the time span of your memory """

    __mapper_args__ = {"polymorphic_identity": "memory_gene"}

    def _mutated_contents(self):
        exp = BanditGame(db.session)
        if exp.allow_memory:
            if random.random() < 0.5:
                return max([int(self.contents) + random.sample([-1, 1], 1)[0], 0])
            else:
                return self.contents
        else:
            return 0


class CuriosityGene(Gene):
    """ A gene that controls your curiosity """

    __mapper_args__ = {"polymorphic_identity": "curiosity_gene"}

    def _mutated_contents(self):
        exp = BanditGame(db.session)
        if exp.allow_curiosity:
            if random.random() < 0.5:
                return min([max([int(self.contents) + random.sample([-1, 1], 1)[0], 1]), 10])
            else:
                return self.contents
        else:
            return 1


class Pull(Info):
    """ An info representing a pull on the arm of a bandit """

    __mapper_args__ = {"polymorphic_identity": "pull"}

    @hybrid_property
    def check(self):
        return self.property1

    @check.setter
    def check(self, check):
        self.property1 = check

    @check.expression
    def check(self):
        return self.property1

    @hybrid_property
    def bandit_id(self):
        return int(self.property2)

    @bandit_id.setter
    def bandit_id(self, bandit_id):
        self.property2 = repr(bandit_id)

    @bandit_id.expression
    def bandit_id(self):
        return cast(self.property2, Integer)

    @hybrid_property
    def remembered(self):
        return self.property3

    @remembered.setter
    def remembered(self, remembered):
        self.property3 = remembered

    @remembered.expression
    def remembered(self):
        return self.property3

    @hybrid_property
    def payoff(self):
        return int(self.property4)

    @payoff.setter
    def payoff(self, payoff):
        self.property4 = repr(payoff)

    @payoff.expression
    def payoff(self):
        return cast(self.property4, Integer)

    @hybrid_property
    def trial(self):
        return int(self.property5)

    @trial.setter
    def trial(self, trial):
        self.property5 = repr(trial)

    @trial.expression
    def trial(self):
        return cast(self.property5, Integer)


class BanditAgent(Agent):

    __mapper_args__ = {"polymorphic_identity": "bandit_agent"}

    @hybrid_property
    def generation(self):
        return int(self.property2)

    @generation.setter
    def generation(self, generation):
        self.property2 = repr(generation)

    @generation.expression
    def generation(self):
        return cast(self.property2, Integer)

    def update(self, infos):
        for info in infos:
            if isinstance(info, Gene):
                self.mutate(info_in=info)

    def calculate_fitness(self):
        exp = BanditGame(db.session)

        my_decisions = Pull.query.filter_by(origin_id=self.id, check="false").all()
        bandits = Bandit.query.filter_by(network_id=self.network_id).all()

        pulls = exp.n_pulls
        curiosity = int(self.infos(type=CuriosityGene)[0].contents)
        memory = int(self.infos(type=MemoryGene)[0].contents)

        fitness = exp.f_min - memory*exp.memory_cost

        for d in my_decisions:
            bandit = [b for b in bandits if b.bandit_id == d.bandit_id][0]
            if int(d.contents) == bandit.treasure_tile:
                fitness += pulls
            if d.remembered == "false":
                fitness -= curiosity

        fitness = max([fitness, 0.0001])
        fitness = ((1.0*fitness)*exp.f_scale_factor)**exp.f_power_factor
        self.fitness = fitness

    def _what(self):
        return Gene


extra_routes = Blueprint(
    'extra_routes', __name__,
    template_folder='templates',
    static_folder='static')


@extra_routes.route("/node/<int:node_id>/calculate_fitness", methods=["GET"])
def calculate_fitness(node_id):

    exp = BanditGame(db.session)
    node = BanditAgent.query.get(node_id)
    if node is None:
        exp.log("Error: /node/{}/calculate_fitness, node {} does not exist".format(node_id))
        page = exp.error_page(error_type="/node/calculate_fitness, node does not exist")
        js = dumps({"status": "error", "html": page})
        return Response(js, status=400, mimetype='application/json')

    node.calculate_fitness()
    exp.save()

    data = {"status": "success"}
    return Response(dumps(data), status=200, mimetype='application/json')


@extra_routes.route("/num_trials", methods=["GET"])
def get_num_trials():
    exp = BanditGame(db.session)
    data = {"status": "success",
            "experiment_repeats": exp.experiment_repeats,
            "practice_repeats": exp.practice_repeats,
            "n_trials": exp.n_trials}
    return Response(dumps(data), status=200, mimetype='application/json')


@extra_routes.route("/num_bandits", methods=["GET"])
def get_num_bandits():
    exp = BanditGame(db.session)
    data = {"status": "success", "num_bandits": exp.n_bandits}
    return Response(dumps(data), status=200, mimetype='application/json')


@extra_routes.route("/num_arms/<int:network_id>/<int:bandit_id>", methods=["GET"])
def get_num_arms(network_id, bandit_id):
    bandit = Bandit.query.filter_by(network_id=network_id, bandit_id=bandit_id).one()
    data = {"status": "success", "num_tiles": bandit.num_tiles}
    return Response(dumps(data), status=200, mimetype='application/json')


@extra_routes.route("/treasure_tile/<int:network_id>/<int:bandit_id>", methods=["GET"])
def get_treasure_tile(network_id, bandit_id):
    bandit = Bandit.query.filter_by(network_id=network_id, bandit_id=bandit_id).one()
    data = {"status": "success", "treasure_tile": bandit.treasure_tile}
    return Response(dumps(data), status=200, mimetype='application/json')


@extra_routes.route("/consent", methods=["GET"])
def get_consent():
    return return_page('consent.html', request)


@extra_routes.route("/instructions/<int:page>", methods=["GET"])
def get_instructions(page):
    exp = BanditGame(db.session)
    return return_page(exp.instruction_pages[page-1], request)


@extra_routes.route("/debrief/<int:page>", methods=["GET"])
def get_debrief(page):
    exp = BanditGame(db.session)
    return return_page(exp.debrief_pages[page-1], request)


@extra_routes.route("/stage", methods=["GET"])
def get_stage():
    return return_page('stage.html', request)


@extra_routes.route("/participant/<worker_id>/<hit_id>/<assignment_id>", methods=["POST"])
def create_participant(worker_id, hit_id, assignment_id):
    exp = BanditGame(db.session)

    parts = Participant.query.filter_by(workerid=worker_id).all()
    if parts:
        print "participant already exists!"
        return Response(status=200)

    p = Participant(workerid=worker_id, assignmentid=assignment_id, hitid=hit_id)
    exp.save(p)
    return Response(status=200)


@extra_routes.route("/ad_address/<mode>/<hit_id>", methods=["GET"])
def ad_address(mode, hit_id):

    if mode == "debug":
        address = '/complete'
    elif mode in ["sandbox", "live"]:
        CONFIG = PsiturkConfig()
        CONFIG.load_config()
        username = os.getenv('psiturk_access_key_id', CONFIG.get("psiTurk Access", "psiturk_access_key_id"))
        password = os.getenv('psiturk_secret_access_id', CONFIG.get("psiTurk Access", "psiturk_secret_access_id"))
        try:
            req = requests.get('https://api.psiturk.org/api/ad/lookup/' + hit_id,
                               auth=(username, password))
        except:
            raise ValueError('api_server_not_reachable')
        else:
            if req.status_code == 200:
                hit_address = req.json()['ad_id']
            else:
                raise ValueError("something here")
        if mode == "sandbox":
            address = 'https://sandbox.ad.psiturk.org/complete/' + str(hit_address)
        elif mode == "live":
            address = 'https://ad.psiturk.org/complete/' + str(hit_address)
    else:
        raise ValueError("Unknown mode: {}".format(mode))
    return Response(dumps({"address": address}), status=200)


def return_page(page, request):
    exp = BanditGame(db.session)
    try:
        hit_id = request.args['hit_id']
        assignment_id = request.args['assignment_id']
        worker_id = request.args['worker_id']
        mode = request.args['mode']
        return render_template(
            page,
            hit_id=hit_id,
            assignment_id=assignment_id,
            worker_id=worker_id,
            mode=mode
        )
    except:
        return exp.error_page(error_type="{} AWS args missing".format(page))


def request_parameter(request, parameter, parameter_type=None, default=None):
    """ Get a parameter from a request

    The request object itself must be passed.
    parameter is the name of the parameter you are looking for
    parameter_type is the type the parameter should have
    default is the value the parameter takes if it has not been passed

    If the parameter is not found and no default is specified,
    or if the parameter is found but is of the wrong type
    then a Response object is returned"""

    exp = BanditGame(db.session)

    # get the parameter
    try:
        value = request.values[parameter]
    except KeyError:
        # if it isnt found use the default, or return an error Response
        if default is not None:
            return default
        else:
            msg = "{} {} request, {} not specified".format(request.url, request.method, parameter)
            exp.log("Error: {}".format(msg))
            data = {
                "status": "error",
                "html": error_page(error_type=msg)
            }
            return Response(
                dumps(data),
                status=400,
                mimetype='application/json')

    # check the parameter type
    if parameter_type is None:
        # if no parameter_type is required, return the parameter as is
        return value
    elif parameter_type == int:
        # if int is required, convert to an int
        try:
            value = int(value)
            return value
        except ValueError:
            msg = "{} {} request, non-numeric {}: {}".format(request.url, request.method, parameter, value)
            exp.log("Error: {}".format(msg))
            data = {
                "status": "error",
                "html": error_page(error_type=msg)
            }
            return Response(
                dumps(data),
                status=400,
                mimetype='application/json')
    elif parameter_type == "known_class":
        # if its a known class check against the known classes
        try:
            value = exp.known_classes[value]
            return value
        except KeyError:
            msg = "{} {} request, unknown_class: {} for parameter {}".format(request.url, request.method, value, parameter)
            exp.log("Error: {}".format(msg))
            data = {
                "status": "error",
                "html": error_page(error_type=msg)
            }
            return Response(
                dumps(data),
                status=400,
                mimetype='application/json')
    elif parameter_type == bool:
        # if its a boolean, convert to a boolean
        if value in ["True", "False"]:
            return value == "True"
        else:
            msg = "{} {} request, non-boolean {}: {}".format(request.url, request.method, parameter, value)
            exp.log("Error: {}".format(msg))
            data = {
                "status": "error",
                "html": error_page(error_type=msg)
            }
            return Response(
                dumps(data),
                status=400,
                mimetype='application/json')
    else:
        msg = "/{} {} request, unknown parameter type: {} for parameter {}".format(request.url, request.method, parameter_type, parameter)
        exp.log("Error: {}".format(msg))
        data = {
            "status": "error",
            "html": error_page(error_type=msg)
        }
        return Response(
            dumps(data),
            status=400,
            mimetype='application/json')


def error_page(participant=None, error_text=None, compensate=True,
               error_type="default"):
    """Render HTML for error page."""
    if error_text is None:

        error_text = """There has been an error and so you are unable to
        continue, sorry! If possible, please return the assignment so someone
        else can work on it."""

        if compensate:
            error_text += """Please use the information below to contact us
            about compensation"""

    if participant is not None:
        hit_id = participant.hitid,
        assignment_id = participant.assignmentid,
        worker_id = participant.workerid
    else:
        hit_id = 'unknown'
        assignment_id = 'unknown'
        worker_id = 'unknown'

    return render_template(
        'error_wallace.html',
        error_text=error_text,
        compensate=compensate,
        contact_address=config.get(
            'HIT Configuration', 'contact_email_on_error'),
        error_type=error_type,
        hit_id=hit_id,
        assignment_id=assignment_id,
        worker_id=worker_id
    )


def date_handler(obj):
    """Serialize dates."""
    return obj.isoformat() if hasattr(obj, 'isoformat') else obj
