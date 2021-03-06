REPOLOC="$(git rev-parse --show-toplevel)"

docker run -it --rm\
            -v $REPOLOC:/home/ceqr-app-data\
            -w /home/ceqr-app-data/\
            sptkl/docker-geosupport:19d bash -c "
            pip install -e .
            cd ceqr/recipes/nysdec_title_v_facility_permits && {
                pip install -r requirements.txt
                python build.py
            cd -;}
            "