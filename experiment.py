""" The Bandit Game! """

from dallinger.experiments import Experiment
from dallinger.models import Network, Vector, Participant
from dallinger.information import Gene
import random
from json import dumps
from flask import Blueprint, Response
from dallinger.config import get_config
config = get_config()
from dallinger import db
session = db.session


def extra_parameters():
    config.register('generation_size', int)
    config.register('generations', int)
    config.register('bonus_payment', float)
    config.register('n_trials', int)
    config.register('n_bandits', int)
    config.register('n_options', int)
    config.register('n_pulls', int)
    config.register('payoff', int)
    config.register('f_min', int)
    config.register('f_scale_factor', float)
    config.register('f_power_factor', int)
    config.register('allow_memory', bool)
    config.register('allow_curiosity', bool)
    config.register('seed_memory', int)
    config.register('seed_curiosity', int)
    config.register('p_move', float)
    config.register('pull_cost', float)
    config.register('memory_cost', float)
    config.register('curiosity_cost', float)


class BanditGame(Experiment):

    def __init__(self, session):
        super(BanditGame, self).__init__(session)
        import models
        self.models = models
        self.task = "The Bandit Game"
        self.verbose = False
        self.experiment_repeats = 1
        self.initial_recruitment_size = config.get("generation_size")
        self.known_classes["Pull"] = self.models.Pull
        self.n_trials = config.get('n_trials')
        self.n_bandits = config.get('n_bandits')
        self.num_arms = config.get('n_options')
        self.p_move = config.get('p_move')

        if not self.networks():
            self.setup()
        self.save()

    def setup(self):
        super(BanditGame, self).setup()
        for net in self.networks():
            net.max_size = config.get('generations')*config.get('generation_size') + 1 + config.get('n_bandits')
            source = self.models.GeneticSource(network=net)
            source.create_genes()
            for bandit in range(self.n_bandits):
                b = self.models.Bandit(network=net)
                b.bandit_id = bandit
                b.num_arms = config.get("n_options")
                b.good_arm = int(random.random()*config.get("n_options")) + 1

    def create_node(self, participant, network):
        """Create a node for a participant."""
        return self.models.BanditAgent(network=network, participant=participant)

    def create_network(self):
        """Return a new network."""
        return self.models.BanditGenerational(generations=config.get("generations"),
                                              generation_size=config.get("generation_size"),
                                              initial_source=True)

    def recruit(self):
        """Recruit participants if necessary."""
        num_approved = len(Participant.query.filter_by(status="approved").all())
        if num_approved % config.get("generation_size") == 0 and num_approved < config.get("generations")*config.get("generation_size"):
            self.log("generation finished, recruiting another")
            self.recruiter().recruit_participants(n=config.get("generation_size"))

    def data_check(self, participant):

        # get the necessary data
        networks = Network.query.all()
        nodes = self.models.BanditAgent.query.filter_by(participant_id=participant.id).all()
        node_ids = [n.id for n in nodes]
        genes = Gene.query.filter(Gene.origin_id.in_(node_ids)).all()
        incoming_vectors = Vector.query.filter(Vector.destination_id.in_(node_ids)).all()
        outgoing_vectors = Vector.query.filter(Vector.origin_id.in_(node_ids)).all()
        decisions = self.models.Pull.query.filter(self.models.Pull.origin_id.in_(node_ids)).all()

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

            # o <= checks <= curiosity
            for node in nodes:
                my_checks = [d for d in decisions if d.check == "true" and d.origin_id == node.id]
                curiosity = int([g for g in genes if g.origin_id == node.id and g.type == "curiosity_gene"][0].contents)
                for t in range(self.n_trials):
                    assert len([d for d in my_checks if d.trial == t]) >= 0
                    assert len([d for d in my_checks if d.trial == t]) <= curiosity

            # all decisions have an int payoff
            for d in decisions:
                if d.check == "false":
                    assert isinstance(int(d.contents), int)

            # all nodes have a fitness
            for node in nodes:
                assert isinstance(node.fitness, float)

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
        nodes = self.models.BanditAgent.query.filter_by(participant_id=participant.id).all()
        nodes = [n for n in nodes if n.network_id in networks_ids]
        bandits = self.models.Bandit.query.all()
        node_ids = [n.id for n in nodes]
        pulls = self.models.Pull.query.filter(self.models.Pull.origin_id.in_(node_ids)).all()

        for node in nodes:
            # for every node get its curiosity and decisions
            decisions = [p for p in pulls if p.origin_id == node.id and p.check == "false"]

            for decision in decisions:
                # for each decision, get the bandit and the right answer
                bandit = [b for b in bandits if b.network_id == node.network_id and b.bandit_id == decision.bandit_id][0]
                right_answer = bandit.good_arm
                num_checks = len([p for p in pulls if p.check == "true" and p.origin_id == decision.origin_id and p.trial == decision.trial])

                # if they get it right score = potential score
                if right_answer == int(decision.contents):
                    score = config.get('n_pulls') - num_checks
                else:
                    score = 0 - num_checks

                # save this info the the decision and update the running totals
                total_score += score

        total_trials = config.get('n_trials') * self.experiment_repeats

        bonus = ((total_score/(1.0*total_trials))-1)/5.0

        bonus = max(min(bonus, 1.0), 0.0)*config.get('bonus_payment')

        bonus = round(bonus, 2)

        return bonus

    def attention_check(self, participant):
        bandits = self.models.Bandit.query.all()
        nodes = self.models.BanditAgent.query.filter_by(participant_id=participant.id).all()
        pulls = []
        for node in nodes:
            pulls.extend(node.infos(type=self.models.Pull))

        final_decisions = [p for p in pulls if p.check == "false"]
        checks = [p for p in pulls if p.check == "true"]

        times_found_treasure = 0
        times_chose_treasure = 0

        for d in final_decisions:
            if d.remembered == "false":
                right_answer = [b for b in bandits if b.network_id == d.network_id and b.bandit_id == d.bandit_id][0].good_arm
                checked_tiles = [int(c.contents) for c in checks if c.network_id == d.network_id and c.trial == d.trial]
                if right_answer in checked_tiles:
                    times_found_treasure += 1
                    if int(d.contents) == right_answer:
                        times_chose_treasure += 1

        diff = times_found_treasure - times_chose_treasure

        return diff < 3


extra_routes = Blueprint(
    'extra_routes', __name__,
    template_folder='templates',
    static_folder='static')


@extra_routes.route("/node/<int:node_id>/calculate_fitness", methods=["GET"])
def calculate_fitness(node_id):
    import models
    node = models.BanditAgent.query.get(node_id)
    node.calculate_fitness()
    session.commit()
    data = {"status": "success"}
    return Response(dumps(data), status=200, mimetype='application/json')


@extra_routes.route("/good_arm/<int:network_id>/<int:bandit_id>", methods=["GET"])
def good_arm(network_id, bandit_id):
    import models
    bandit = models.Bandit.query.filter_by(network_id=network_id, bandit_id=bandit_id).one()
    data = {"status": "success", "good_arm": bandit.good_arm}
    return Response(dumps(data), status=200, mimetype='application/json')
